# Auto-Apply Feature Guide

This guide explains how to use the automated job application system integrated into the Job Finder web app.

## Overview

The auto-apply feature consists of two main workflows:

1. **Question Discovery** - Extract questions from job application forms without applying
2. **Auto-Apply** - Automatically fill and submit job applications using your pre-filled answers

## Architecture

```
┌─────────────────┐
│  Job Detail     │  User clicks "Discover Questions"
│  Page           │
└────────┬────────┘
         │
         v
┌─────────────────────────┐
│ Question Discovery      │  Navigates to job page, extracts form fields
│ Service                 │  Saves questions to JSON file
└────────┬────────────────┘
         │
         v
┌─────────────────────────┐
│ data/application_       │  Questions stored by company/job
│ questions/              │
└─────────────────────────┘
         │
         v
┌─────────────────────────┐
│ User fills out          │  User downloads template and fills answers
│ user_answers.json       │
└────────┬────────────────┘
         │
         v
┌─────────────────────────┐
│ Auto-Apply              │  User clicks "Auto-Apply" button
│ Orchestrator            │
└────────┬────────────────┘
         │
         v
┌─────────────────────────┐
│ Playwright fills        │  Form is filled and submitted automatically
│ and submits             │
└─────────────────────────┘
```

## Step-by-Step Usage

### Step 1: Discover Questions

1. Browse jobs and open any job detail page
2. Click the **"🔍 Discover Questions"** button in the "Automated Application" section
3. Wait 10-30 seconds while the system:
   - Navigates to the job application page
   - Dismisses cookie banners
   - Extracts all form fields (text inputs, dropdowns, checkboxes, etc.)
   - Saves questions to `data/application_questions/{company}_{job_title}.json`
4. You'll see a success message with the number of questions discovered
5. Click "View All Questions →" to see all discovered questions

### Step 2: View and Manage Questions

Visit the **Questions** page (accessible from the top navigation):

- **All Discovered Questions**: See all question files organized by company/job
- **Unique Questions**: See all unique questions grouped together across all jobs
- **Download Template**: Click "📥 Download Profile Template" to get a JSON template with all questions

### Step 3: Fill Out Your Profile

You need to create two files:

#### 3.1 `data/profile.json`

Your standard profile (skills, experience, etc.). Example:

```json
{
  "personal": {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "phone": "+1234567890",
    "linkedin": "https://linkedin.com/in/johndoe",
    "github": "https://github.com/johndoe",
    "portfolio": "https://johndoe.com"
  },
  "professional": {
    "current_title": "Senior Software Engineer",
    "years_experience": 5,
    "skills": ["Python", "JavaScript", "AWS", "Docker"],
    "location": "San Francisco, CA",
    "work_authorization": "US Citizen",
    "visa_sponsorship": "No"
  }
}
```

#### 3.2 `data/user_answers.json`

Your answers to application questions. Download the template from the Questions page, then fill it out:

```json
{
  "personal_info": {
    "first_name": {
      "answer": "John"
    },
    "last_name": {
      "answer": "Doe"
    },
    "email": {
      "answer": "john.doe@example.com"
    },
    "phone": {
      "answer": "+1234567890"
    },
    "linkedin": {
      "answer": "https://linkedin.com/in/johndoe"
    }
  },
  "professional": {
    "years_experience": {
      "answer": "5"
    },
    "work_authorization": {
      "answer": "US Citizen"
    },
    "visa_sponsorship": {
      "answer": "No"
    },
    "salary_expectations": {
      "answer": "150000"
    },
    "start_date": {
      "answer": "2 weeks"
    }
  },
  "custom_questions": {
    "why_interested_in_role": {
      "answer": "I'm passionate about building scalable systems..."
    },
    "describe_technical_challenge": {
      "answer": "In my previous role, I optimized our API..."
    }
  }
}
```

#### 3.3 `data/cv_library/resume.pdf`

Your resume/CV in PDF format. Place it in the `data/cv_library/` folder.

### Step 4: Auto-Apply

1. Go to any job detail page
2. Make sure you've completed Step 3 (profile and answers are filled out)
3. Click the **"⚡ Auto-Apply"** button
4. Confirm the application
5. Wait 1-2 minutes while the system:
   - Loads your profile and answers
   - Navigates to the job application page
   - Fills out all form fields automatically
   - Uploads your resume if required
   - Submits the application
6. You'll see a success/failure message with details

## File Structure

```
job-finder/
├── data/
│   ├── profile.json                      # Your profile (create this)
│   ├── user_answers.json                 # Your answers (create this)
│   ├── cv_library/
│   │   └── resume.pdf                    # Your CV (create this)
│   └── application_questions/            # Auto-generated
│       ├── netflix_software_engineer.json
│       ├── meta_frontend_developer.json
│       └── ...
├── answers/
│   ├── applied/                          # Successful applications
│   │   └── {company}_{job}_{timestamp}.json
│   └── not_applied/                      # Failed attempts
│       └── {company}_{job}_{timestamp}.json
└── web/
    ├── app.py                            # Flask routes
    └── question_discovery.py             # Discovery service
```

## API Endpoints

### `POST /api/discover-questions/<job_id>`

Discover questions for a specific job.

**Response:**
```json
{
  "success": true,
  "job_url": "https://...",
  "company": "Netflix",
  "job_title": "Software Engineer",
  "questions_count": 15,
  "questions": [...],
  "questions_file": "/path/to/file.json"
}
```

### `GET /api/all-questions`

Get all discovered question files.

**Response:**
```json
{
  "success": true,
  "total_files": 5,
  "files": [
    {
      "filename": "netflix_software_engineer.json",
      "company": "Netflix",
      "job_title": "Software Engineer",
      "questions_count": 15,
      "job_url": "https://..."
    }
  ]
}
```

### `GET /api/unique-questions`

Get all unique questions grouped together.

**Response:**
```json
{
  "success": true,
  "unique_count": 25,
  "questions": {
    "first_name": [
      {
        "company": "Netflix",
        "job_title": "Software Engineer",
        "question": "First Name",
        "type": "text",
        "required": true
      }
    ]
  }
}
```

### `GET /api/profile-template`

Generate a profile template with all discovered questions.

**Response:**
```json
{
  "success": true,
  "template": {
    "personal_info": {...},
    "professional": {...},
    "custom_questions": {...}
  }
}
```

### `POST /api/auto-apply/<job_id>`

Auto-apply to a specific job.

**Request Body:**
```json
{
  "wait_for_user": false
}
```

**Response:**
```json
{
  "applied": true,
  "artifact": "/path/to/submission.json",
  "steps": 3
}
```

## Troubleshooting

### "Missing required files" error

**Solution**: Make sure these files exist:
- `data/profile.json`
- `data/user_answers.json`
- `data/cv_library/resume.pdf`

### "No apply flow found" error

**Solution**: The job page doesn't have a detectable application form. Some companies use external ATS systems that may be harder to detect. Try:
1. Manually check if the job has an online application form
2. Check if the job redirects to a third-party site

### Questions not being filled correctly

**Solution**: 
1. Check that your `user_answers.json` has the right field names
2. Review the discovered questions file to see exact field IDs
3. Ensure your answers match the expected format (e.g., dates, dropdowns)

### Application submitted but marked as failed

**Solution**: 
1. Check the artifact file in `answers/not_applied/` for details
2. Look at the browser automation logs
3. Some forms have hidden validation that requires manual review

## Tips for Best Results

1. **Discover questions from multiple jobs first** - This helps you see common patterns
2. **Fill out answers completely** - Leave no required fields blank
3. **Use consistent formatting** - Dates, phone numbers, etc. should match expected formats
4. **Test on one job first** - Before bulk applying, test the workflow on a single job
5. **Review discovered questions** - Check the Questions page to ensure questions were extracted correctly
6. **Keep your CV updated** - Make sure `resume.pdf` is current

## Security & Privacy

- Your profile and answers are stored **locally** on your machine
- No data is sent to external servers except the job application sites themselves
- The automation runs in your local browser (Playwright)
- You can review all submissions in the `answers/` directory

## Limitations

- Not all job application systems are supported (some use iframe/complex JavaScript)
- CAPTCHA and anti-bot measures may block automation
- Some companies require manual verification steps
- Video/phone screening questions cannot be automated

## Next Steps

After setting up auto-apply:
1. Browse jobs on the main page
2. Discover questions from 3-5 jobs to build your answer base
3. Download and fill out the profile template
4. Test auto-apply on one job
5. Review the results in `answers/applied/`
6. Iterate and improve your answers based on results

## Support

For issues or questions:
- Check the logs in the terminal where Flask is running
- Review artifact files in `answers/` directory
- Examine DOM snapshots in `output/dom_snapshots/` to debug form detection
