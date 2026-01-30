"""Netflix Job Application Automation with AI-Powered Auto-Fill.

This script automates the job application process on Netflix's careers portal.
It can either prompt the user interactively OR use AI + profile data to
automatically answer questions and fill forms.

Usage:
    # Interactive mode (prompts for each field)
    python tools/scrapers/netflix_apply.py --url "https://explore.jobs.netflix.net/careers?pid=790304856703..."
    
    # AI-powered auto mode (uses profile + Gemini)
    python tools/scrapers/netflix_apply.py --url "..." --auto --profile /path/to/profile.md
    
    # Using job ID
    python tools/scrapers/netflix_apply.py --job-id 790304856703 --auto
"""

import asyncio
import argparse
import sys
import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright.async_api import async_playwright, Page, ElementHandle, Locator
from utils.logging import get_logger
from agents.common.gemini_client import GeminiClient, GeminiConfig

logger = get_logger(__name__)


class FieldType(Enum):
    """Types of form fields we can encounter."""
    TEXT = "text"
    TEXTAREA = "textarea"
    EMAIL = "email"
    PHONE = "phone"
    SELECT = "select"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    FILE = "file"
    DATE = "date"
    UNKNOWN = "unknown"


@dataclass
class FormField:
    """Represents a form field in the application."""
    name: str
    label: str
    field_type: FieldType
    required: bool = False
    options: list[str] = field(default_factory=list)
    placeholder: str = ""
    current_value: str = ""
    element_selector: str = ""


@dataclass
class ApplicationProgress:
    """Track the progress of a job application."""
    job_title: str = ""
    job_id: str = ""
    current_step: int = 0
    total_steps: int = 0
    fields_filled: list[str] = field(default_factory=list)
    submitted: bool = False


class ProfileParser:
    """Parse profile.md into structured data for auto-fill."""
    
    def __init__(self, profile_path: str):
        self.profile_path = profile_path
        self.raw_content = ""
        self.data = {}
        self._load_and_parse()
    
    def _load_and_parse(self):
        """Load and parse the profile markdown file."""
        with open(self.profile_path, 'r') as f:
            self.raw_content = f.read()
        
        # Extract key fields using regex
        self.data = {
            # Personal Info
            "full_name": self._extract_name(),
            "first_name": self._extract_name().split()[0] if self._extract_name() else "",
            "last_name": " ".join(self._extract_name().split()[1:]) if self._extract_name() else "",
            "email": self._extract_pattern(r'Email:\s*(\S+@\S+)'),
            "phone": self._extract_pattern(r'Phone:\s*(\+?[\d\(\)\-\s]+)'),
            "phone_clean": self._clean_phone(),
            "country_code": "+44",  # Default UK
            "location": self._extract_pattern(r'\*\*Location:\*\*\s*([^\n]+)'),
            "city": self._extract_city(),
            "country": "United Kingdom",
            "linkedin": self._extract_pattern(r'LinkedIn:\s*(\S+)'),
            "github": self._extract_pattern(r'GitHub:\s*(\S+)'),
            
            # Work Authorization
            "work_authorization": self._extract_pattern(r'\*\*Work Authorization:\*\*\s*([^\n]+)'),
            "requires_sponsorship": False,  # British Citizen
            
            # Professional
            "summary": self._extract_section("Summary"),
            "skills": self._extract_section("Technical Skills"),
            "experience": self._extract_section("Experience"),
            "education": self._extract_section("Education"),
            "languages": self._extract_section("Languages Spoken"),
            "interests": self._extract_section("Interests"),
        }
    
    def _extract_name(self) -> str:
        """Extract name from first heading."""
        match = re.search(r'^#\s+(.+)$', self.raw_content, re.MULTILINE)
        return match.group(1).strip() if match else ""
    
    def _extract_pattern(self, pattern: str) -> str:
        """Extract a value using regex pattern."""
        match = re.search(pattern, self.raw_content)
        return match.group(1).strip() if match else ""
    
    def _extract_city(self) -> str:
        """Extract city from location."""
        location = self._extract_pattern(r'\*\*Location:\*\*\s*([^\n]+)')
        if location:
            return location.split(',')[0].strip()
        return ""
    
    def _clean_phone(self) -> str:
        """Clean phone number to digits only."""
        phone = self._extract_pattern(r'Phone:\s*(\+?[\d\(\)\-\s]+)')
        # Remove +44(0) prefix and clean
        phone = re.sub(r'\+44\(0\)', '', phone)
        phone = re.sub(r'[^\d]', '', phone)
        return phone
    
    def _extract_section(self, section_name: str) -> str:
        """Extract content under a section heading."""
        pattern = rf'##\s*{section_name}\s*\n(.*?)(?=\n##|\Z)'
        match = re.search(pattern, self.raw_content, re.DOTALL)
        return match.group(1).strip() if match else ""
    
    def get_field_value(self, field_label: str) -> Optional[str]:
        """Get auto-fill value for a field based on its label."""
        label_lower = field_label.lower()
        
        # Skip these patterns - don't match them to profile values
        skip_patterns = ["sponsor", "require", "legally work", "authorization", "visa"]
        if any(pattern in label_lower for pattern in skip_patterns):
            return None
        
        # Direct mappings - must be exact or near-exact matches
        exact_mappings = {
            "email": self.data["email"],
            "e-mail": self.data["email"],
            "first name": self.data["first_name"],
            "first_name": self.data["first_name"],
            "firstname": self.data["first_name"],
            "last name": self.data["last_name"],
            "last_name": self.data["last_name"],
            "lastname": self.data["last_name"],
            "surname": self.data["last_name"],
            "full name": self.data["full_name"],
            "name": self.data["full_name"],
            "phone": self.data["phone_clean"],
            "phone number": self.data["phone_clean"],
            "mobile": self.data["phone_clean"],
            "telephone": self.data["phone_clean"],
            "country code": self.data["country_code"],
            "city": self.data["city"],
            "linkedin": self.data["linkedin"],
            "github": self.data["github"],
        }
        
        # Check exact mappings first
        for key, value in exact_mappings.items():
            if key in label_lower:
                return value
        
        # These are more generic and should only match if the label is JUST this word
        # "country" - only match if label is exactly "country" or "country *"
        if label_lower == "country" or label_lower == "country *" or label_lower.startswith("country ") and "code" not in label_lower:
            return self.data["country"]
        
        # "location" - only match if label is exactly "location"
        if label_lower == "location" or label_lower == "location *":
            return self.data["location"]
        
        return None


class AIAnswerGenerator:
    """Use Gemini to generate answers for application questions."""
    
    def __init__(self, profile_content: str, job_title: str = ""):
        self.profile_content = profile_content
        self.job_title = job_title
        self.client = GeminiClient(GeminiConfig(
            model="gemini-2.0-flash",
            temperature=0.3,
            system_instruction=self._get_system_prompt(),
        ))
    
    def _get_system_prompt(self) -> str:
        return f"""You are an expert job application assistant helping a candidate apply for jobs.
You have access to their profile and must answer application questions professionally and accurately.

CANDIDATE PROFILE:
{self.profile_content}

APPLYING FOR: {self.job_title}

RULES:
1. Answer questions based ONLY on the profile provided
2. Be concise but thorough - match the expected answer length
3. For yes/no questions, answer definitively based on the profile
4. For multiple choice, pick the BEST matching option
5. For open-ended questions, write professionally in first person
6. Never make up information not in the profile
7. If asked about salary expectations, be reasonable for the role/location
8. If asked about availability, say "2 weeks notice" or "immediately available"
9. For work authorization in UK - the candidate is a British Citizen (no sponsorship needed)
10. For EU - the candidate has European Citizenship (eligible to work)
"""
    
    def generate_answer(
        self, 
        question: str, 
        field_type: str,
        options: list[str] = None,
        placeholder: str = ""
    ) -> str:
        """Generate an answer for a form field."""
        
        prompt = f"""Answer this job application question:

QUESTION: {question}
FIELD TYPE: {field_type}
{f'OPTIONS: {", ".join(options)}' if options else ''}
{f'HINT: {placeholder}' if placeholder else ''}

Provide ONLY the answer value, no explanation. For multiple choice, return the exact option text.
If this is a yes/no question, answer with just "Yes" or "No".
If you cannot answer from the profile, respond with "SKIP"."""

        try:
            response = self.client.generate_text(prompt)
            answer = response.strip()
            
            # Clean up response
            if answer.startswith('"') and answer.endswith('"'):
                answer = answer[1:-1]
            
            return answer if answer != "SKIP" else None
            
        except Exception as e:
            logger.warning(f"AI answer generation failed: {e}")
            return None
    
    def select_best_option(self, question: str, options: list[str]) -> Optional[str]:
        """Select the best option from a list for a multiple choice question."""
        if not options:
            return None
        
        prompt = f"""Select the BEST option for this job application question.

QUESTION: {question}
OPTIONS:
{chr(10).join(f'{i+1}. {opt}' for i, opt in enumerate(options))}

Return ONLY the number (1, 2, 3, etc.) of the best option based on the candidate profile.
If none apply or you're unsure, return the number of the most neutral/common option."""

        try:
            response = self.client.generate_text(prompt)
            # Extract number from response
            match = re.search(r'\d+', response)
            if match:
                idx = int(match.group()) - 1
                if 0 <= idx < len(options):
                    return options[idx]
            return options[0]  # Default to first option
        except Exception as e:
            logger.warning(f"Option selection failed: {e}")
            return options[0] if options else None


class NetflixJobApplicator:
    """Handles the Netflix job application process with optional AI auto-fill."""
    
    BASE_URL = "https://explore.jobs.netflix.net/careers"
    
    def __init__(
        self, 
        headless: bool = False,
        auto_mode: bool = False,
        profile_path: Optional[str] = None,
        resume_path: Optional[str] = None,
        cover_letter_path: Optional[str] = None,
    ):
        """
        Initialize the applicator.
        
        Args:
            headless: Run browser in headless mode
            auto_mode: Use AI to automatically answer questions
            profile_path: Path to profile.md for auto-fill
            resume_path: Path to resume/CV file
            cover_letter_path: Path to cover letter file
        """
        self.headless = headless
        self.auto_mode = auto_mode
        self.page: Optional[Page] = None
        self.progress = ApplicationProgress()
        
        # Profile and AI
        self.profile: Optional[ProfileParser] = None
        self.ai: Optional[AIAnswerGenerator] = None
        self.resume_path = resume_path
        self.cover_letter_path = cover_letter_path
        
        if profile_path and os.path.exists(profile_path):
            self.profile = ProfileParser(profile_path)
            logger.info(f"✅ Loaded profile: {self.profile.data['full_name']}")
        
    async def start_application(self, job_url: str) -> None:
        """
        Start the application process for a job.
        
        Args:
            job_url: Full URL to the job posting or application page
        """
        logger.info(f"🚀 Starting application for: {job_url}")
        if self.auto_mode:
            logger.info("🤖 AUTO MODE ENABLED - AI will answer questions")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            self.page = await context.new_page()
            
            try:
                # Navigate to job page
                await self._navigate_to_job(job_url)
                
                # Initialize AI with job context
                if self.auto_mode and self.profile:
                    self.ai = AIAnswerGenerator(
                        self.profile.raw_content,
                        self.progress.job_title
                    )
                    logger.info("🧠 AI initialized with profile and job context")
                
                # Click Apply Now button
                await self._click_apply_button()
                
                # Process the application form
                await self._process_application_form()
                
            except KeyboardInterrupt:
                logger.info("\n⏹️  Application cancelled by user")
            except Exception as e:
                logger.error(f"❌ Error during application: {e}")
            finally:
                # Keep browser open for user to review before closing
                if not self.headless:
                    try:
                        input("\n📋 Press Enter to close the browser...")
                    except:
                        pass
                try:
                    await browser.close()
                except:
                    pass  # Browser might already be closed
    
    async def _navigate_to_job(self, job_url: str) -> None:
        """Navigate to the job posting page."""
        logger.info("📄 Loading job page...")
        await self.page.goto(job_url, wait_until="networkidle", timeout=30000)
        await self.page.wait_for_timeout(2000)
        
        # Dismiss cookie consent banner if present
        await self._dismiss_cookie_consent()
        
        # Extract job title
        title_el = await self.page.query_selector("h1.position-title, h1")
        if title_el:
            self.progress.job_title = (await title_el.inner_text()).strip()
            logger.info(f"📌 Job: {self.progress.job_title}")
        
        # Extract job ID from URL
        match = re.search(r'pid=(\d+)', job_url) or re.search(r'/job/(\d+)', job_url)
        if match:
            self.progress.job_id = match.group(1)
    
    async def _dismiss_cookie_consent(self) -> None:
        """Dismiss cookie consent banners."""
        try:
            # OneTrust cookie consent (Netflix uses this)
            consent_selectors = [
                "#onetrust-accept-btn-handler",  # Accept cookies button
                ".onetrust-close-btn-handler",   # Close button
                "[id*='onetrust'] button:has-text('Accept')",
                "[id*='onetrust'] button:has-text('Accept All')",
                "[id*='cookie'] button:has-text('Accept')",
                ".cookie-consent-accept",
            ]
            
            for selector in consent_selectors:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn:
                        await btn.click()
                        logger.debug("🍪 Dismissed cookie consent")
                        await self.page.wait_for_timeout(500)
                        return
                except:
                    continue
        except Exception as e:
            logger.debug(f"Cookie consent handling: {e}")
    
    async def _click_apply_button(self) -> None:
        """Find and click the Apply Now button."""
        logger.info("🔍 Looking for Apply button...")
        
        # Try multiple selectors for the apply button
        apply_selectors = [
            "button:has-text('APPLY NOW')",
            "button:has-text('Apply Now')",
            "button:has-text('Apply')",
            "a:has-text('APPLY NOW')",
            "a:has-text('Apply Now')",
            "[data-testid='apply-button']",
            ".apply-button",
        ]
        
        for selector in apply_selectors:
            try:
                btn = await self.page.wait_for_selector(selector, timeout=3000)
                if btn:
                    logger.info("✅ Found Apply button, clicking...")
                    await btn.click()
                    await self.page.wait_for_timeout(3000)
                    return
            except:
                continue
        
        raise Exception("Could not find Apply button on the page")
    
    async def _process_application_form(self) -> None:
        """Process the application form step by step."""
        logger.info("\n" + "=" * 60)
        logger.info("📝 STARTING APPLICATION FORM")
        logger.info("=" * 60)
        
        print("\n💡 Instructions:")
        print("   - Answer each question when prompted")
        print("   - Type 'skip' to skip optional fields")
        print("   - Type 'quit' to cancel the application")
        print("   - For file uploads, provide the full file path")
        print()
        
        step = 0
        max_steps = 20  # Safety limit
        
        while step < max_steps:
            step += 1
            self.progress.current_step = step
            
            # Wait for form to stabilize
            await self.page.wait_for_timeout(1000)
            
            # Check if we're done (confirmation page, success message, etc.)
            if await self._check_application_complete():
                break
            
            # Find all form fields on current page/step
            fields = await self._detect_form_fields()
            
            if not fields:
                # No fields found - might be a transition page or we need to click Next
                next_clicked = await self._try_click_next_button()
                if not next_clicked:
                    logger.warning("⚠️  No form fields found and no Next button")
                    break
                continue
            
            logger.info(f"\n📋 Step {step}: Found {len(fields)} field(s)")
            
            # Process each field
            for field in fields:
                await self._process_field(field)
            
            # Try to proceed to next step
            await self._try_click_next_button()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ APPLICATION FORM COMPLETED")
        logger.info("=" * 60)
    
    async def _detect_form_fields(self) -> list[FormField]:
        """Detect all form fields on the current page."""
        fields = []
        
        # Text inputs
        text_inputs = await self.page.query_selector_all(
            "input[type='text']:visible, input[type='email']:visible, "
            "input[type='tel']:visible, input[type='number']:visible, "
            "input:not([type]):visible"
        )
        
        for inp in text_inputs:
            field = await self._parse_input_field(inp)
            if field:
                fields.append(field)
        
        # Textareas
        textareas = await self.page.query_selector_all("textarea:visible")
        for ta in textareas:
            field = await self._parse_textarea_field(ta)
            if field:
                fields.append(field)
        
        # Native select dropdowns
        selects = await self.page.query_selector_all("select:visible")
        logger.debug(f"Found {len(selects)} native select elements")
        
        for idx, sel in enumerate(selects):
            field = await self._parse_select_field(sel)
            if field:
                fields.append(field)
        
        # CUSTOM DROPDOWNS - Netflix uses these instead of native <select>
        # Look for elements that look like dropdowns (have listbox role, aria-expanded, etc.)
        custom_dropdowns = await self._detect_custom_dropdowns()
        fields.extend(custom_dropdowns)
        
        # File inputs
        file_inputs = await self.page.query_selector_all("input[type='file']")
        for fi in file_inputs:
            field = await self._parse_file_field(fi)
            if field:
                fields.append(field)
        
        # Radio button groups
        radio_groups = await self._detect_radio_groups()
        fields.extend(radio_groups)
        
        # Checkbox groups
        checkbox_fields = await self._detect_checkboxes()
        fields.extend(checkbox_fields)
        
        # Deduplicate fields by normalizing labels and keeping first occurrence
        seen_labels = set()
        unique_fields = []
        for field in fields:
            # Normalize label: remove trailing *, strip whitespace
            normalized = field.label.rstrip('*').strip().lower()
            # Skip garbage labels
            if len(normalized) < 3 or "careerslocations" in normalized:
                continue
            if normalized not in seen_labels:
                seen_labels.add(normalized)
                unique_fields.append(field)
        
        return unique_fields
    
    async def _detect_custom_dropdowns(self) -> list[FormField]:
        """Detect custom dropdown components (not native <select> elements).
        Netflix/Eightfold uses custom dropdowns with specific patterns."""
        fields = []
        
        try:
            # Find all custom dropdown-like elements
            # These typically have role="listbox", aria-haspopup, or specific class patterns
            dropdown_data = await self.page.evaluate("""() => {
                const dropdowns = [];
                
                // Find elements that look like custom dropdowns
                // Look for common patterns: button with aria-haspopup, combobox role, etc.
                const selectors = [
                    '[role="combobox"]',
                    '[role="listbox"]',
                    '[aria-haspopup="listbox"]',
                    'button[aria-expanded]',
                    '[class*="dropdown"][class*="toggle"]',
                    '[class*="select"][class*="button"]',
                    '[class*="SelectTrigger"]',
                    '[class*="Dropdown"]',
                ];
                
                const seen = new Set();
                
                for (const selector of selectors) {
                    document.querySelectorAll(selector).forEach(el => {
                        // Skip if already processed or not visible
                        if (seen.has(el) || el.offsetParent === null) return;
                        seen.add(el);
                        
                        // Find the container with the question
                        let container = el.closest('[class*="field"], [class*="question"], [class*="form-group"], form > div');
                        if (!container) container = el.parentElement?.parentElement;
                        
                        // Get question text
                        let questionText = '';
                        if (container) {
                            const clone = container.cloneNode(true);
                            // Remove the dropdown button text
                            clone.querySelectorAll('button, [role="combobox"], [role="listbox"]').forEach(b => b.remove());
                            const text = clone.innerText?.trim() || '';
                            const lines = text.split('\\n').filter(l => l.trim().length > 3);
                            for (const line of lines) {
                                if (line.toLowerCase() !== 'select' && line.length > 5) {
                                    questionText = line.trim();
                                    break;
                                }
                            }
                        }
                        
                        // Get current value from button/trigger
                        const currentValue = el.innerText?.trim() || el.getAttribute('aria-label') || '';
                        
                        // Check for required indicator
                        const isRequired = container?.innerText?.includes('*') || 
                                          container?.querySelector('[class*="required"]') !== null ||
                                          el.getAttribute('aria-required') === 'true';
                        
                        dropdowns.push({
                            questionText: questionText,
                            currentValue: currentValue,
                            isRequired: isRequired,
                            ariaLabel: el.getAttribute('aria-label') || '',
                            id: el.id || '',
                            // Get a selector to find this element later
                            selector: el.id ? '#' + el.id : null
                        });
                    });
                }
                
                return dropdowns;
            }""")
            
            logger.debug(f"Found {len(dropdown_data)} custom dropdown elements")
            
            for dd in dropdown_data:
                question = dd.get('questionText', '') or dd.get('ariaLabel', '') or dd.get('currentValue', '')
                if not question or question.lower() == 'select':
                    # Skip dropdowns with no meaningful label - they'll be detected by other means
                    continue
                
                # For custom dropdowns, we can't easily get options without clicking
                # So we mark them and handle them specially
                fields.append(FormField(
                    name=dd.get('id', ''),
                    label=question,
                    field_type=FieldType.SELECT,
                    required=dd.get('isRequired', False),
                    options=[],  # Options would need clicking to reveal
                    placeholder=dd.get('currentValue', 'Select'),
                ))
                
        except Exception as e:
            logger.debug(f"Error detecting custom dropdowns: {e}")
        
        return fields
    
    async def _parse_input_field(self, element: ElementHandle) -> Optional[FormField]:
        """Parse a text input field."""
        try:
            input_type = await element.get_attribute("type") or "text"
            name = await element.get_attribute("name") or ""
            placeholder = await element.get_attribute("placeholder") or ""
            required = await element.get_attribute("required") is not None
            aria_label = await element.get_attribute("aria-label") or ""
            
            # Try to find associated label
            element_id = await element.get_attribute("id")
            label = ""
            if element_id:
                label_el = await self.page.query_selector(f"label[for='{element_id}']")
                if label_el:
                    label = (await label_el.inner_text()).strip()
            
            # SPECIAL CASE: If placeholder is "Select", this is a custom dropdown
            # We need to find the question text from the container
            if placeholder.lower() == "select" and not label:
                try:
                    container_text = await element.evaluate("""el => {
                        const container = el.closest('[class*="field"], [class*="form-group"], [class*="question"]') || el.parentElement?.parentElement;
                        if (container) {
                            // Get text but exclude the input's placeholder
                            const clone = container.cloneNode(true);
                            clone.querySelectorAll('input, select, option').forEach(e => e.remove());
                            const text = clone.innerText?.trim() || '';
                            // Get first meaningful line
                            const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 3 && l.toLowerCase() !== 'select');
                            return lines[0] || '';
                        }
                        return '';
                    }""")
                    if container_text:
                        label = container_text
                        # This is actually a SELECT-like field
                        return FormField(
                            name=name,
                            label=label,
                            field_type=FieldType.SELECT,
                            required=required,
                            options=[],  # Options will be shown when clicked
                            placeholder=placeholder,
                        )
                except Exception as e:
                    logger.debug(f"Error getting container text for Select input: {e}")
            
            # Use aria-label or placeholder as fallback
            label = label or aria_label or placeholder or name
            
            if not label:
                return None
            
            field_type = FieldType.TEXT
            if input_type == "email":
                field_type = FieldType.EMAIL
            elif input_type == "tel":
                field_type = FieldType.PHONE
            elif input_type == "date":
                field_type = FieldType.DATE
            
            return FormField(
                name=name,
                label=label,
                field_type=field_type,
                required=required,
                placeholder=placeholder,
            )
        except:
            return None
    
    async def _parse_textarea_field(self, element: ElementHandle) -> Optional[FormField]:
        """Parse a textarea field."""
        try:
            name = await element.get_attribute("name") or ""
            placeholder = await element.get_attribute("placeholder") or ""
            required = await element.get_attribute("required") is not None
            aria_label = await element.get_attribute("aria-label") or ""
            
            element_id = await element.get_attribute("id")
            label = ""
            if element_id:
                label_el = await self.page.query_selector(f"label[for='{element_id}']")
                if label_el:
                    label = (await label_el.inner_text()).strip()
            
            label = label or aria_label or placeholder or name
            
            if not label:
                return None
            
            return FormField(
                name=name,
                label=label,
                field_type=FieldType.TEXTAREA,
                required=required,
                placeholder=placeholder,
            )
        except:
            return None
    
    async def _parse_select_field(self, element: ElementHandle) -> Optional[FormField]:
        """Parse a select dropdown field - SIMPLIFIED and DIRECT approach."""
        try:
            # Get EVERYTHING in one JavaScript call for reliability
            field_data = await element.evaluate("""el => {
                // Get basic attributes
                const name = el.name || '';
                const id = el.id || '';
                const required = el.required || el.hasAttribute('required');
                const ariaLabel = el.getAttribute('aria-label') || '';
                
                // Get ALL options directly
                const options = [];
                for (const opt of el.options) {
                    const text = opt.text?.trim() || opt.innerText?.trim() || '';
                    if (text && text.toLowerCase() !== 'select' && text !== '--' && text !== '') {
                        options.push(text);
                    }
                }
                
                // Find the question/label text - go up the DOM tree
                let questionText = '';
                let container = el.parentElement;
                
                // Try up to 5 parent levels
                for (let i = 0; i < 5 && container && !questionText; i++) {
                    // Get all text in container except the select itself
                    const clone = container.cloneNode(true);
                    const selects = clone.querySelectorAll('select, option');
                    selects.forEach(s => s.remove());
                    
                    const fullText = clone.innerText?.trim() || '';
                    
                    // Split by newlines and find the question
                    const lines = fullText.split('\\n').map(l => l.trim()).filter(l => l.length > 3);
                    
                    for (const line of lines) {
                        // Skip if it's just "Select" or an option
                        if (line.toLowerCase() === 'select' || options.includes(line)) continue;
                        
                        // Check if it looks like a question
                        const lower = line.toLowerCase();
                        if (line.includes('?') || 
                            lower.includes('are you') || 
                            lower.includes('do you') ||
                            lower.includes('have you') ||
                            lower.includes('would you') ||
                            lower.includes('will you') ||
                            lower.includes('please') ||
                            lower.includes('select') && line.length > 20) {
                            questionText = line;
                            break;
                        }
                    }
                    
                    // If no question found, take the first meaningful line
                    if (!questionText && lines.length > 0) {
                        for (const line of lines) {
                            if (line.toLowerCase() !== 'select' && !options.includes(line) && line.length > 5) {
                                questionText = line;
                                break;
                            }
                        }
                    }
                    
                    container = container.parentElement;
                }
                
                // Also try label[for]
                if (!questionText && id) {
                    const labelEl = document.querySelector('label[for="' + id + '"]');
                    if (labelEl) {
                        questionText = labelEl.innerText?.trim() || '';
                    }
                }
                
                // Use aria-label as fallback
                if (!questionText && ariaLabel) {
                    questionText = ariaLabel;
                }
                
                return {
                    name: name,
                    id: id,
                    required: required,
                    options: options,
                    questionText: questionText,
                    ariaLabel: ariaLabel,
                    optionCount: el.options.length
                };
            }""")
            
            name = field_data.get("name", "")
            required = field_data.get("required", False)
            options = field_data.get("options", [])
            question_text = field_data.get("questionText", "")
            option_count = field_data.get("optionCount", 0)
            
            # Log for debugging
            logger.debug(f"SELECT: question='{question_text[:50]}...' options={options[:3]} total_options={option_count}")
            
            # Build the label
            label = question_text or field_data.get("ariaLabel", "") or name or "Select"
            
            # If label is still just "Select" and we have options, show them
            if label.lower() == "select" and options:
                label = f"Select ({', '.join(options[:3])}{'...' if len(options) > 3 else ''})"
            
            # Warn if we couldn't find the question
            if "select" in label.lower() and (required or options):
                print(f"   ⚠️ DEBUG: Could not find question text. Options: {options[:5]}, Total: {option_count}")
            
            return FormField(
                name=name,
                label=label,
                field_type=FieldType.SELECT,
                required=required,
                options=options,
            )
        except Exception as e:
            logger.error(f"Error parsing select field: {e}")
            return None
    
    async def _parse_file_field(self, element: ElementHandle) -> Optional[FormField]:
        """Parse a file upload field."""
        try:
            name = await element.get_attribute("name") or ""
            accept = await element.get_attribute("accept") or ""
            aria_label = await element.get_attribute("aria-label") or ""
            
            # Try to find label - file inputs often have complex structures
            label = aria_label or name or "File Upload"
            is_resume = False
            is_cover_letter = False
            
            # Check parent/ancestor elements for context
            try:
                # Look for label in parent hierarchy
                parent_text = await element.evaluate("""el => {
                    let parent = el.parentElement;
                    for (let i = 0; i < 5 && parent; i++) {
                        const text = parent.innerText || '';
                        if (text.length < 500) return text;
                        parent = parent.parentElement;
                    }
                    return '';
                }""")
                
                parent_lower = parent_text.lower()
                if "resume" in parent_lower or "cv" in parent_lower:
                    label = "Resume/CV"
                    is_resume = True
                elif "cover letter" in parent_lower:
                    label = "Cover Letter"
                    is_cover_letter = True
                elif "additional" in parent_lower or "other" in parent_lower:
                    label = "Additional Document"
            except:
                pass
            
            # Also check the accept attribute for hints
            if not is_resume and not is_cover_letter:
                if ".pdf" in accept and ".doc" in accept:
                    # Generic document upload - assume first is resume
                    label = "Resume/CV"
                    is_resume = True
            
            return FormField(
                name=name,
                label=label,
                field_type=FieldType.FILE,
                placeholder=f"Accepted formats: {accept}" if accept else "",
            )
        except:
            return None
    
    async def _detect_radio_groups(self) -> list[FormField]:
        """Detect radio button groups."""
        fields = []
        
        try:
            # Find fieldsets or divs containing radio buttons
            radio_containers = await self.page.query_selector_all(
                "fieldset:has(input[type='radio']), "
                "[role='radiogroup'], "
                ".radio-group"
            )
            
            for container in radio_containers:
                legend = await container.query_selector("legend, .legend, label:first-child")
                label = ""
                if legend:
                    label = (await legend.inner_text()).strip()
                
                options = []
                radio_labels = await container.query_selector_all("label")
                for rl in radio_labels:
                    opt_text = (await rl.inner_text()).strip()
                    if opt_text and opt_text != label:
                        options.append(opt_text)
                
                if label and options:
                    fields.append(FormField(
                        name="",
                        label=label,
                        field_type=FieldType.RADIO,
                        options=options,
                    ))
        except:
            pass
        
        return fields
    
    async def _detect_checkboxes(self) -> list[FormField]:
        """Detect checkbox fields."""
        fields = []
        
        try:
            checkboxes = await self.page.query_selector_all("input[type='checkbox']:visible")
            
            for cb in checkboxes:
                element_id = await cb.get_attribute("id")
                name = await cb.get_attribute("name") or ""
                
                label = ""
                if element_id:
                    label_el = await self.page.query_selector(f"label[for='{element_id}']")
                    if label_el:
                        label = (await label_el.inner_text()).strip()
                
                if not label:
                    # Try to get text from parent
                    parent_text = await cb.evaluate("el => el.parentElement.innerText")
                    label = parent_text.strip()[:100]  # Limit length
                
                if label:
                    fields.append(FormField(
                        name=name,
                        label=label,
                        field_type=FieldType.CHECKBOX,
                    ))
        except:
            pass
        
        return fields
    
    async def _process_field(self, field: FormField) -> None:
        """Process a single form field - auto-fill with AI or prompt user."""
        req_marker = " *" if field.required else ""
        
        print(f"\n{'─' * 50}")
        print(f"📝 {field.label}{req_marker}")
        
        # Always show options for SELECT/RADIO fields - this is critical for user to understand the question
        if field.field_type in [FieldType.SELECT, FieldType.RADIO]:
            if field.options:
                print(f"   📋 Options: {', '.join(field.options[:20])}")
                if len(field.options) > 20:
                    print(f"   ... and {len(field.options) - 20} more")
            else:
                print("   ⚠️  No options detected for this dropdown!")
        
        # Warn user if we couldn't detect the question
        if field.label.lower() == "select" or field.label.startswith("Select ("):
            print("   ❓ WARNING: Could not detect question text from page!")
            if field.options:
                print(f"   💡 Based on options, this might be asking about: {field.options[0] if field.options else 'unknown'}")
        
        if field.placeholder and field.placeholder.lower() != "select":
            print(f"   💡 {field.placeholder}")
        
        # Try auto-fill in auto mode
        user_input = None
        if self.auto_mode:
            user_input = await self._get_auto_answer(field)
            if user_input:
                print(f"   🤖 Auto-answer: {user_input[:100]}{'...' if len(str(user_input)) > 100 else ''}")
        
        # Fall back to manual input if no auto answer
        if user_input is None:
            user_input = await self._get_manual_input(field)
        
        # Handle special commands
        if isinstance(user_input, str):
            if user_input.lower() == "quit":
                raise KeyboardInterrupt("User quit")
            
            if user_input.lower() == "skip":
                if field.required:
                    print("   ⚠️  This field is required, cannot skip")
                    return await self._process_field(field)  # Retry
                print("   ⏭️  Skipped")
                return
        
        if user_input is None or user_input == "":
            if field.required:
                print("   ⚠️  No answer available, falling back to manual input")
                user_input = await self._get_manual_input(field)
            else:
                print("   ⏭️  Skipped (no answer)")
                return
        
        # Fill the field
        await self._fill_field(field, user_input)
        self.progress.fields_filled.append(field.label)
        print("   ✅ Filled")
    
    async def _get_auto_answer(self, field: FormField) -> Optional[str]:
        """Get auto-fill answer from profile or AI."""
        logger.debug(f"_get_auto_answer: '{field.label}' type={field.field_type.value} options={field.options}")
        
        # 1. Try direct profile mapping first (fast, no API call)
        if self.profile:
            profile_value = self.profile.get_field_value(field.label)
            if profile_value:
                return profile_value
        
        # 2. Handle file uploads
        if field.field_type == FieldType.FILE:
            label_lower = field.label.lower()
            if "resume" in label_lower or "cv" in label_lower:
                if self.resume_path and os.path.exists(self.resume_path):
                    return self.resume_path
            elif "cover" in label_lower:
                if self.cover_letter_path and os.path.exists(self.cover_letter_path):
                    return self.cover_letter_path
            return None  # Can't auto-fill files without paths
        
        # 3. Handle demographic checkboxes (gender, ethnicity, etc.)
        if field.field_type == FieldType.CHECKBOX:
            return self._handle_demographic_checkbox(field.label)
        
        # 4. Handle select/radio with options - try smart selection
        if field.field_type in [FieldType.SELECT, FieldType.RADIO] and field.options:
            # Try to auto-select based on common patterns
            auto_selection = self._smart_select_option(field.label, field.options)
            if auto_selection:
                return auto_selection
            
            # Fall back to AI if available
            if self.ai:
                return self.ai.select_best_option(field.label, field.options)
            
            # Last resort: select first non-placeholder option
            for opt in field.options:
                if opt.lower() not in ["select", "choose", "--", "", "please select"]:
                    return opt
            return field.options[0] if field.options else None
        
        # 4b. Handle SELECT without options (custom dropdowns) - these are demographic questions
        if field.field_type == FieldType.SELECT and not field.options:
            label_lower = field.label.lower()
            logger.debug(f"4b: Processing SELECT without options: '{field.label}'")
            
            # For Netflix-specific questions - MUST CHECK THESE FIRST
            if "netflix" in label_lower and "contractor" in label_lower:
                logger.debug(f"  -> Matched Netflix contractor")
                return "No"
            
            if "netflix" in label_lower and ("worked" in label_lower or "past" in label_lower or "subsidiar" in label_lower):
                logger.debug(f"  -> Matched Netflix past")
                return "No"
            
            # For sponsorship questions - British citizen doesn't need sponsorship
            # Check for: "Do you require sponsorship to legally work in the job location?"
            if "sponsorship" in label_lower or "sponsor" in label_lower:
                logger.debug(f"  -> Matched sponsorship")
                return "No"
            if "legally work" in label_lower:
                logger.debug(f"  -> Matched legally work")
                return "No"
            if "require" in label_lower and "work" in label_lower:
                logger.debug(f"  -> Matched require work")
                return "No"
            
            # For country selection
            if label_lower == "country" or label_lower == "location" or label_lower.startswith("country"):
                logger.debug(f"  -> Matched country")
                return "United Kingdom"
            
            # For demographic questions, type "I choose not to disclose" or "Prefer not to answer"
            demographic_keywords = ["transgender", "caregiver", "dependent", "disability", 
                                   "disabled", "veteran", "military", "gender", "ethnicity",
                                   "race", "sexual", "orientation"]
            if any(kw in label_lower for kw in demographic_keywords):
                logger.debug(f"  -> Matched demographic")
                return "I choose not to disclose"
            
            logger.debug(f"  -> No match, returning None")
            # Don't fall through to AI for custom dropdowns - let it be handled manually
            return None
        
        # 5. Use AI for open-ended questions
        if self.ai:
            return self.ai.generate_answer(
                field.label,
                field.field_type.value,
                field.options,
                field.placeholder
            )
        
        return None
    
    def _handle_demographic_checkbox(self, label: str) -> Optional[str]:
        """Handle demographic survey checkboxes - prefer 'I choose not to disclose'."""
        label_lower = label.lower()
        
        # STRATEGY: For all demographic questions, select "I choose not to disclose" / "Prefer not to say"
        # This is the safest and most privacy-respecting approach
        
        # Check if this IS the "prefer not to disclose" option - SELECT IT
        decline_phrases = [
            "choose not to disclose", "prefer not to", "prefer not to say",
            "decline to answer", "do not wish", "rather not say"
        ]
        if any(phrase in label_lower for phrase in decline_phrases):
            return "yes"  # Select this option!
        
        # Gender options - don't select any specific gender
        gender_options = ["man", "woman", "non-binary", "agender", "genderfluid", 
                         "genderqueer", "gender non-conforming", "transgender"]
        if any(g == label_lower or label_lower.startswith(g + " ") for g in gender_options):
            return "no"
        
        # Ethnicity options - don't select any specific ethnicity  
        ethnicity_keywords = ["asian", "black", "arab", "chinese", "indian", "pakistani", 
                            "bangladeshi", "caribbean", "african", "irish", "gypsy", 
                            "welsh", "scottish", "british", "white", "mixed", "other ethnic"]
        if any(kw in label_lower for kw in ethnicity_keywords):
            return "no"
        
        # Sexuality options - don't select any specific sexuality
        sexuality_options = ["heterosexual", "gay", "lesbian", "bisexual", "pansexual", 
                           "asexual", "queer", "homosexual", "straight"]
        if any(s in label_lower for s in sexuality_options):
            return "no"
        
        # Disability disclosure - prefer not to disclose
        if "disability" in label_lower or "disabled" in label_lower:
            return "no"
        
        # Transgender experience - prefer not to disclose
        if "transgender" in label_lower or "trans " in label_lower:
            return "no"
        
        # Caregiver status - prefer not to disclose
        if "caregiver" in label_lower or "dependent" in label_lower or "primary care" in label_lower:
            return "no"
        
        # Veteran status - prefer not to disclose  
        if "veteran" in label_lower or "military" in label_lower:
            return "no"
        
        # "Not Listed" option - don't select
        if "not listed" in label_lower:
            return "no"
        
        # Auto-accept agreements/consents
        if any(word in label_lower for word in ["agree", "consent", "acknowledge", "confirm", "accept"]):
            return "yes"
        
        return None
    
    def _smart_select_option(self, label: str, options: list[str]) -> Optional[str]:
        """Smart selection of dropdown options based on common patterns."""
        if not options:
            return None
        
        label_lower = label.lower()
        options_lower = [o.lower() for o in options]
        
        # ============================================================
        # Netflix-specific questions
        # ============================================================
        
        # "Are you currently working for Netflix as a contractor?"
        if "working for netflix" in label_lower or "netflix" in label_lower and "contractor" in label_lower:
            for i, opt in enumerate(options_lower):
                if opt == "no" or "no" in opt:
                    return options[i]
        
        # "Have you worked for Netflix or any of Netflix's subsidiaries in the past?"
        if "worked for netflix" in label_lower or ("netflix" in label_lower and "past" in label_lower):
            for i, opt in enumerate(options_lower):
                if opt == "no" or "no" in opt:
                    return options[i]
        
        # "Do you require sponsorship to legally work in the job location?"
        if "require sponsorship" in label_lower or "sponsorship" in label_lower:
            for i, opt in enumerate(options_lower):
                if opt == "no" or "no" in opt:  # British citizen - no sponsorship needed
                    return options[i]
        
        # FALLBACK: If options are just Yes/No and label has key words
        if set(options_lower) == {"yes", "no"} or set(options_lower) == {"no", "yes"}:
            # For contractor/past employee questions, answer No
            if any(kw in label_lower for kw in ["contractor", "employee", "worked", "employed"]):
                for i, opt in enumerate(options_lower):
                    if opt == "no":
                        return options[i]
            # For sponsorship questions, answer No (if authorized to work)
            if any(kw in label_lower for kw in ["sponsor", "authorization", "visa", "legally work"]):
                for i, opt in enumerate(options_lower):
                    if opt == "no":
                        return options[i]
        
        # ============================================================
        # Generic patterns
        # ============================================================
        
        # Country code - select UK (+44) by searching "United Kingdom"
        if "country code" in label_lower or any("+44" in o or "+1" in o for o in options):
            # Return "United Kingdom" to trigger the search behavior in _fill_field
            for i, opt in enumerate(options):
                if "united kingdom" in opt.lower():
                    return options[i]
            # Fallback: return United Kingdom as search term
            return "United Kingdom"
        
        # Country selection - prefer UK
        if "country" in label_lower:
            for i, opt in enumerate(options_lower):
                if "united kingdom" in opt or opt == "uk" or "britain" in opt:
                    return options[i]
        
        # ============================================================
        # Demographic dropdown questions - select "prefer not to disclose"
        # ============================================================
        
        # Transgender experience question
        if "transgender" in label_lower or "trans experience" in label_lower:
            for i, opt in enumerate(options_lower):
                if "prefer not" in opt or "choose not" in opt or "decline" in opt:
                    return options[i]
        
        # Caregiver/dependent question
        if "caregiver" in label_lower or "dependent" in label_lower or "primary care" in label_lower:
            for i, opt in enumerate(options_lower):
                if "prefer not" in opt or "choose not" in opt or "decline" in opt:
                    return options[i]
        
        # Disability question
        if "disability" in label_lower or "disabled" in label_lower:
            for i, opt in enumerate(options_lower):
                if "prefer not" in opt or "choose not" in opt or "decline" in opt:
                    return options[i]
        
        # Generic "Prefer not to say" / "I choose not to disclose" for demographic dropdowns
        decline_phrases = ["prefer not", "choose not to disclose", "decline", "rather not"]
        for i, opt in enumerate(options_lower):
            if any(phrase in opt for phrase in decline_phrases):
                return options[i]
        
        # Work authorization / visa status - select options indicating no sponsorship needed
        if "authorization" in label_lower or "visa" in label_lower or "sponsor" in label_lower:
            for i, opt in enumerate(options_lower):
                if "citizen" in opt or "no sponsor" in opt or "authorized" in opt or "indefinite" in opt:
                    return options[i]
            # Also check for "no" if asking "do you require sponsorship"
            for i, opt in enumerate(options_lower):
                if opt == "no":
                    return options[i]
        
        # Generic yes/no questions about current employment at the company
        if "currently working" in label_lower or "currently employed" in label_lower:
            for i, opt in enumerate(options_lower):
                if opt == "no":
                    return options[i]
        
        # Generic yes/no questions about past employment
        if "worked" in label_lower and "past" in label_lower:
            for i, opt in enumerate(options_lower):
                if opt == "no":
                    return options[i]
        
        # How did you hear about us - prefer LinkedIn or Job Board
        if "hear about" in label_lower or "how did you" in label_lower or "source" in label_lower:
            for i, opt in enumerate(options_lower):
                if "linkedin" in opt or "job board" in opt or "website" in opt:
                    return options[i]
        
        # Notice period / availability
        if "notice" in label_lower or "start" in label_lower or "available" in label_lower:
            for i, opt in enumerate(options_lower):
                if "2 week" in opt or "immediate" in opt or "1 month" in opt:
                    return options[i]
        
        # Experience level
        if "experience" in label_lower or "years" in label_lower:
            for i, opt in enumerate(options_lower):
                if "3" in opt or "4" in opt or "5" in opt or "3-5" in opt:
                    return options[i]
        
        # Salary expectations - if it's a dropdown with ranges
        if "salary" in label_lower or "compensation" in label_lower:
            # Select middle-ish option
            if len(options) >= 3:
                return options[len(options) // 2]
        
        return None
    
    async def _get_manual_input(self, field: FormField) -> str:
        """Get manual input from user for a field."""
        if field.field_type == FieldType.FILE:
            return input(f"   📁 Enter file path (or 'skip'): ").strip()
        elif field.field_type == FieldType.TEXTAREA:
            print("   📝 Enter text (press Enter twice to finish):")
            lines = []
            while True:
                line = input("   ")
                if line == "":
                    if lines and lines[-1] == "":
                        lines.pop()
                        break
                    lines.append("")
                else:
                    lines.append(line)
            return "\n".join(lines)
        elif field.field_type == FieldType.CHECKBOX:
            return input(f"   ☑️  Check this box? (y/n/skip): ").strip().lower()
        elif field.field_type == FieldType.RADIO:
            for i, opt in enumerate(field.options, 1):
                print(f"      {i}. {opt}")
            return input(f"   🔘 Enter number or 'skip': ").strip()
        elif field.field_type == FieldType.SELECT:
            return input(f"   📋 Enter selection (or 'skip'): ").strip()
        else:
            return input(f"   ✏️  Enter value (or 'skip'): ").strip()
    
    async def _handle_privacy_popup(self) -> None:
        """Handle the Candidate Privacy acknowledgment popup that appears after resume upload."""
        try:
            # Wait briefly for popup to appear
            await asyncio.sleep(0.5)
            
            # Look for the "I Acknowledge" button
            acknowledge_btn = await self.page.query_selector(
                "button:has-text('I Acknowledge'), "
                "button:has-text('Acknowledge'), "
                "[role='button']:has-text('I Acknowledge'), "
                "a:has-text('I Acknowledge')"
            )
            
            if acknowledge_btn:
                logger.info("🔒 Privacy popup detected - clicking 'I Acknowledge'")
                await acknowledge_btn.click()
                await asyncio.sleep(0.3)
                return
            
            # Alternative: look for modal with privacy text and find the button
            modal = await self.page.query_selector(
                "[role='dialog'], .modal, [class*='modal'], [class*='popup'], [class*='dialog']"
            )
            if modal:
                modal_text = await modal.inner_text()
                if "privacy" in modal_text.lower() or "acknowledge" in modal_text.lower():
                    btn = await modal.query_selector(
                        "button:not(:has-text('Cancel')), "
                        "[role='button']:not(:has-text('Cancel'))"
                    )
                    if btn:
                        btn_text = await btn.inner_text()
                        if "acknowledge" in btn_text.lower() or "accept" in btn_text.lower():
                            logger.info(f"🔒 Clicking '{btn_text.strip()}' on privacy popup")
                            await btn.click()
                            await asyncio.sleep(0.3)
        except Exception as e:
            logger.debug(f"Privacy popup handling: {e}")
    
    async def _find_custom_dropdown_for_field(self, field: FormField) -> Optional[ElementHandle]:
        """Find the custom dropdown input element for a given field."""
        try:
            # Find inputs with placeholder="Select"
            inputs = await self.page.query_selector_all("input[placeholder='Select']:visible, input[placeholder='select']:visible")
            
            for inp in inputs:
                container_text = await inp.evaluate("""el => {
                    const container = el.closest('[class*="field"], [class*="form-group"], [class*="question"]') || el.parentElement?.parentElement;
                    return container?.innerText?.substring(0, 500) || '';
                }""")
                
                # Check if the container text matches our field label
                if field.label.lower() in container_text.lower():
                    return inp
                
                # Also check for partial match on key words
                label_words = [w for w in field.label.lower().split() if len(w) > 3]
                if label_words and all(w in container_text.lower() for w in label_words[:3]):
                    return inp
            
            return None
        except Exception as e:
            logger.debug(f"Error finding custom dropdown: {e}")
            return None
    
    async def _fill_custom_dropdown(self, input_el: ElementHandle, value: str, label: str) -> None:
        """Fill a custom dropdown (Netflix/Eightfold style) by clicking and selecting."""
        try:
            # Click to open the dropdown
            await input_el.click()
            await asyncio.sleep(0.5)
            
            # Wait for dropdown to appear
            dropdown = await self.page.wait_for_selector(
                "[role='listbox'], [class*='dropdown'][class*='open'], [class*='menu-container']",
                timeout=2000
            )
            
            if dropdown:
                # Try to find and click the matching option
                value_lower = value.lower()
                
                # Look for exact match first
                option = await dropdown.query_selector(f"[role='option']:has-text('{value}')")
                
                if not option:
                    # Try partial matches for common patterns
                    options = await dropdown.query_selector_all("[role='option'], [class*='menu-item'] button")
                    
                    for opt in options:
                        opt_text = (await opt.inner_text()).strip().lower()
                        
                        # Check various match conditions
                        if value_lower in opt_text or opt_text in value_lower:
                            option = opt
                            break
                        
                        # For "I choose not to disclose" -> match "prefer not" or "choose not" or "not applicable"
                        if "choose not" in value_lower or "prefer not" in value_lower:
                            if "prefer not" in opt_text or "choose not" in opt_text or "not applicable" in opt_text or "decline" in opt_text:
                                option = opt
                                break
                        
                        # For "No" answers
                        if value_lower == "no" and opt_text == "no":
                            option = opt
                            break
                        
                        # For "Yes" answers
                        if value_lower == "yes" and opt_text == "yes":
                            option = opt
                            break
                        
                        # For country
                        if "united kingdom" in value_lower and "united kingdom" in opt_text:
                            option = opt
                            break
                
                if option:
                    await option.click()
                    logger.debug(f"Selected option for '{label}'")
                    await asyncio.sleep(0.3)
                else:
                    # No matching option found - try typing the value
                    logger.debug(f"No exact match found, typing value: {value}")
                    await self.page.keyboard.type(value, delay=30)
                    await asyncio.sleep(0.3)
                    await self.page.keyboard.press("Enter")
            else:
                # Dropdown didn't open - just type the value
                await input_el.fill(value)
                
        except Exception as e:
            logger.debug(f"Error filling custom dropdown '{label}': {e}")
            # Fallback: try to just type the value
            try:
                await input_el.fill('')
                await input_el.fill(value)
            except:
                pass
    
    async def _fill_field(self, field: FormField, value: str) -> None:
        """Fill a form field with the provided value."""
        try:
            if field.field_type == FieldType.FILE:
                # Handle file upload
                file_input = await self.page.query_selector(f"input[type='file'][name='{field.name}']")
                if not file_input:
                    file_input = await self.page.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(value)
                    # Handle privacy popup that may appear after resume upload
                    await self._handle_privacy_popup()
            
            elif field.field_type == FieldType.SELECT:
                # First try native select
                select = await self.page.query_selector(f"select[name='{field.name}']")
                if not select:
                    selects = await self.page.query_selector_all("select:visible")
                    for s in selects:
                        if field.name and field.name in str(await s.get_attribute("name") or ""):
                            select = s
                            break
                
                if select:
                    # Native select handling
                    try:
                        await select.select_option(label=value)
                        return
                    except:
                        try:
                            await select.select_option(value=value)
                            return
                        except:
                            pass
                
                # CUSTOM DROPDOWN: Find input with placeholder="Select" that matches our label
                # These are custom dropdowns used by Netflix/Eightfold
                custom_dropdown = await self._find_custom_dropdown_for_field(field)
                if custom_dropdown:
                    await self._fill_custom_dropdown(custom_dropdown, value, field.label)
                    return
                
                # Last resort: try to find any input that might be the dropdown
                label_lower = field.label.lower()
                inputs = await self.page.query_selector_all("input[placeholder='Select']:visible")
                for inp in inputs:
                    try:
                        container_text = await inp.evaluate("""el => {
                            const container = el.closest('[class*="field"]') || el.parentElement?.parentElement;
                            return container?.innerText?.substring(0, 200) || '';
                        }""")
                        if any(word in container_text.lower() for word in field.label.lower().split()[:3]):
                            await self._fill_custom_dropdown(inp, value, field.label)
                            return
                    except:
                        continue
            
            elif field.field_type == FieldType.CHECKBOX:
                if value.lower() in ["y", "yes", "true", "1"]:
                    checkbox = await self.page.query_selector(
                        f"input[type='checkbox'][name='{field.name}']"
                    )
                    if not checkbox:
                        checkbox = await self.page.query_selector("input[type='checkbox']")
                    if checkbox:
                        await checkbox.check()
            
            elif field.field_type == FieldType.RADIO:
                # Value should be index (1-based) or option text
                try:
                    idx = int(value) - 1
                    if 0 <= idx < len(field.options):
                        option_text = field.options[idx]
                    else:
                        option_text = value
                except ValueError:
                    option_text = value
                
                # Click the radio button with matching label
                radio = await self.page.query_selector(
                    f"input[type='radio'][value='{option_text}']"
                )
                if not radio:
                    # Try to find by label text
                    label = await self.page.query_selector(f"label:has-text('{option_text}')")
                    if label:
                        await label.click()
                        return
                
                if radio:
                    await radio.click()
            
            elif field.field_type == FieldType.TEXTAREA:
                textarea = await self.page.query_selector(f"textarea[name='{field.name}']")
                if not textarea:
                    textarea = await self.page.query_selector("textarea")
                if textarea:
                    # Clear field first (triple-click to select all, then type)
                    await textarea.click(click_count=3)
                    await textarea.fill(value)
            
            else:  # TEXT, EMAIL, PHONE, DATE
                # Find input by name
                selector = f"input[name='{field.name}']"
                input_el = await self.page.query_selector(selector)
                
                if not input_el:
                    # Try to find by placeholder or aria-label
                    inputs = await self.page.query_selector_all("input:visible")
                    for inp in inputs:
                        placeholder = await inp.get_attribute("placeholder") or ""
                        aria = await inp.get_attribute("aria-label") or ""
                        if field.label.lower() in placeholder.lower() or field.label.lower() in aria.lower():
                            input_el = inp
                            break
                
                if input_el:
                    # Check if it's editable first
                    is_editable = await input_el.is_editable()
                    if is_editable:
                        # Clear the field first by filling with empty then with value
                        await input_el.fill('')
                        await input_el.fill(value)
                    else:
                        # Might be an autocomplete - try clicking and typing
                        await self._fill_autocomplete_field(field.label, value)
        
        except Exception as e:
            logger.warning(f"⚠️  Could not fill field '{field.label}': {e}")
    
    async def _fill_autocomplete_field(self, label: str, value: str) -> None:
        """Handle autocomplete/typeahead fields (like Eightfold location pickers)."""
        try:
            # Find the field container by label
            label_el = await self.page.query_selector(f"label:has-text('{label}')")
            if label_el:
                # Click on the label's container to activate it
                container = await label_el.evaluate_handle("el => el.closest('.form-group, .input-group, [class*=\"field\"]')")
                if container:
                    await container.as_element().click()
            
            # Type the value (this often triggers autocomplete)
            await self.page.keyboard.type(value, delay=50)
            await self.page.wait_for_timeout(1000)
            
            # Try to click the first autocomplete suggestion
            suggestion_selectors = [
                ".autocomplete-suggestion:first-child",
                ".suggestion-item:first-child",
                "[role='option']:first-child",
                ".dropdown-item:first-child",
                "[class*='suggestion']:first-child",
                "[class*='option']:first-child",
            ]
            
            for selector in suggestion_selectors:
                try:
                    suggestion = await self.page.query_selector(selector)
                    if suggestion and await suggestion.is_visible():
                        await suggestion.click()
                        return
                except:
                    continue
            
            # If no suggestion found, just press Enter
            await self.page.keyboard.press("Enter")
            
        except Exception as e:
            logger.warning(f"⚠️  Autocomplete handling failed for '{label}': {e}")
    
    async def _try_click_next_button(self) -> bool:
        """Try to click Next/Continue/Submit button."""
        next_selectors = [
            "button:has-text('Next')",
            "button:has-text('Continue')",
            "button:has-text('Submit')",
            "button:has-text('Save')",
            "button[type='submit']",
            "input[type='submit']",
            ".next-button",
            ".continue-button",
        ]
        
        for selector in next_selectors:
            try:
                btn = await self.page.query_selector(selector)
                if btn and await btn.is_visible():
                    btn_text = await btn.inner_text()
                    logger.info(f"➡️  Clicking '{btn_text.strip()}'...")
                    await btn.click()
                    await self.page.wait_for_timeout(2000)
                    return True
            except:
                continue
        
        return False
    
    async def _check_application_complete(self) -> bool:
        """Check if the application has been completed."""
        # Look for success indicators
        success_indicators = [
            "Application submitted",
            "Thank you for applying",
            "Application received",
            "Successfully submitted",
            "We have received your application",
        ]
        
        try:
            page_text = await self.page.inner_text("body")
            for indicator in success_indicators:
                if indicator.lower() in page_text.lower():
                    logger.info(f"🎉 Application complete: '{indicator}'")
                    self.progress.submitted = True
                    return True
        except:
            pass
        
        return False


async def apply_to_job(
    job_url: str,
    headless: bool = False,
    auto_mode: bool = False,
    profile_path: Optional[str] = None,
    resume_path: Optional[str] = None,
    cover_letter_path: Optional[str] = None,
) -> ApplicationProgress:
    """
    Apply to a Netflix job with optional AI auto-fill.
    
    Args:
        job_url: URL to the job posting
        headless: Run in headless mode (default False for interactive)
        auto_mode: Use AI + profile to auto-answer questions
        profile_path: Path to profile.md file
        resume_path: Path to resume/CV PDF
        cover_letter_path: Path to cover letter PDF
    
    Returns:
        ApplicationProgress with details about the application
    """
    applicator = NetflixJobApplicator(
        headless=headless,
        auto_mode=auto_mode,
        profile_path=profile_path,
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
    )
    await applicator.start_application(job_url)
    return applicator.progress


# Default paths
DEFAULT_PROFILE_PATH = "/Users/alperenturkmen/Downloads/profile.md"
DEFAULT_RESUME_PATH = None  # Set to your resume path, e.g., "/Users/alperenturkmen/Downloads/CV.pdf"


def main():
    parser = argparse.ArgumentParser(
        description="Apply to Netflix jobs with AI-powered auto-fill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Interactive mode (prompts for each field)
    python netflix_apply.py --url "https://explore.jobs.netflix.net/careers?pid=790304856703..."
    
    # AI auto-fill mode (uses profile + Gemini)
    python netflix_apply.py --url "..." --auto
    python netflix_apply.py --url "..." --auto --profile ~/profile.md
    
    # With resume and cover letter
    python netflix_apply.py --url "..." --auto --resume ~/cv.pdf --cover-letter ~/cover.pdf
    
    # Using job ID
    python netflix_apply.py --job-id 790304856703 --auto
        """
    )
    
    parser.add_argument(
        "--url",
        type=str,
        help="Full URL to the job posting"
    )
    parser.add_argument(
        "--job-id",
        type=str,
        help="Netflix job ID (will construct URL automatically)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (default: visible browser)"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Enable AI auto-fill mode using profile and Gemini"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=DEFAULT_PROFILE_PATH,
        help=f"Path to profile.md file (default: {DEFAULT_PROFILE_PATH})"
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=DEFAULT_RESUME_PATH,
        help=f"Path to resume/CV PDF (default: {DEFAULT_RESUME_PATH})"
    )
    parser.add_argument(
        "--cover-letter",
        type=str,
        help="Path to cover letter PDF"
    )
    
    args = parser.parse_args()
    
    # Construct URL
    if args.url:
        job_url = args.url
    elif args.job_id:
        job_url = f"https://explore.jobs.netflix.net/careers/job/{args.job_id}"
    else:
        # Default to the example URL
        job_url = "https://explore.jobs.netflix.net/careers?location=London%2C%20England%2C%20United%20Kingdom&pid=790304856703&domain=netflix.com&sort_by=relevance"
        print(f"No URL provided, using default: {job_url}")
    
    print("\n" + "=" * 60)
    print("🎬 NETFLIX JOB APPLICATION ASSISTANT")
    print("=" * 60)
    print(f"\n📍 Job URL: {job_url}")
    
    if args.auto:
        print(f"\n🤖 AUTO MODE ENABLED")
        print(f"   Profile: {args.profile}")
        print(f"   Resume: {args.resume}")
        if args.cover_letter:
            print(f"   Cover Letter: {args.cover_letter}")
    else:
        print("\n📝 INTERACTIVE MODE - you'll be prompted for each field")
    
    print("\n⚠️  Note: Keep the browser window focused during the process")
    print("💡 Press Ctrl+C at any time to cancel\n")
    
    try:
        # Run the application
        progress = asyncio.run(apply_to_job(
            job_url,
            headless=args.headless,
            auto_mode=args.auto,
            profile_path=args.profile,
            resume_path=args.resume,
            cover_letter_path=args.cover_letter,
        ))
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 APPLICATION SUMMARY")
        print("=" * 60)
        print(f"   Job: {progress.job_title}")
        print(f"   Job ID: {progress.job_id}")
        print(f"   Fields filled: {len(progress.fields_filled)}")
        print(f"   Submitted: {'✅ Yes' if progress.submitted else '❌ No'}")
        print("=" * 60)
    except KeyboardInterrupt:
        print("\n\n⏹️  Application cancelled")
    except Exception as e:
        logger.error(f"Application error: {e}")


if __name__ == "__main__":
    main()
