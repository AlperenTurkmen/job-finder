"""
Job Listing Normalizer

Normalizes job listings from various scrapers into a standardized format.
Each scraper has different fields - this module maps them to a common
schema for consistent storage and processing.

Usage:
    from tools.scrapers.job_listing_normalizer import normalize_job, normalize_jobs
    
    # Single job
    standard_job = normalize_job("netflix", netflix_job)
    
    # Multiple jobs
    standard_jobs = normalize_jobs("google", google_jobs)
"""

from dataclasses import dataclass, field, asdict
from typing import Any
import json


@dataclass
class NormalizedJobListing:
    """Normalized job listing format for all scrapers.
    
    Attributes:
        title: Job title
        location: Primary job location
        other_locations: Additional locations for the role (if multi-location)
        department: Department or team name
        work_location_option: "onsite", "remote", "hybrid", or "" if unknown
        job_id: Company's job reference ID
        posted_date: When the job was posted (if available)
        job_url: Direct URL to the job posting
        company: Company name
    """
    title: str
    location: str
    other_locations: list[str] = field(default_factory=list)
    department: str = ""
    work_location_option: str = ""  # "onsite", "remote", "hybrid", ""
    job_id: str = ""
    posted_date: str = ""
    job_url: str = ""
    company: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


# Mapping configuration for each scraper
# Format: standard_field -> {source_field, transform (optional)}
SCRAPER_MAPPINGS: dict[str, dict[str, Any]] = {
    "netflix": {
        "title": "title",
        "location": "location",
        "other_locations": {"field": "locations", "transform": "list_except_primary"},
        "department": "department",
        "work_location_option": "work_location_option",
        "job_id": "job_id",
        "posted_date": None,  # Netflix doesn't provide this
        "job_url": "job_url",
        "company": {"value": "Netflix"},
    },
    "meta": {
        "title": "title",
        "location": "location",
        "other_locations": {"field": "locations", "transform": "list_except_primary"},
        "department": {"field": "teams", "transform": "first_item"},
        "work_location_option": None,  # Meta doesn't provide this in listing
        "job_id": "job_id",
        "posted_date": None,
        "job_url": "job_url",
        "company": {"value": "Meta"},
    },
    "samsung": {
        "title": "title",
        "location": "location",
        "other_locations": None,
        "department": None,
        "work_location_option": {"field": "remote_type", "transform": "lowercase"},
        "job_id": "job_id",
        "posted_date": {"field": "posted_on", "transform": "strip_posted"},
        "job_url": "job_url",
        "company": {"value": "Samsung"},
    },
    "vodafone": {
        "title": "title",
        "location": "location",
        "other_locations": {"field": "locations", "transform": "list_except_primary"},
        "department": "department",
        "work_location_option": "work_location_option",
        "job_id": "display_job_id",
        "posted_date": None,
        "job_url": "job_url",
        "company": {"value": "Vodafone"},
    },
    "rockstar": {
        "title": "title",
        "location": {"field": "company", "transform": "rockstar_location"},
        "other_locations": None,
        "department": "department",
        "work_location_option": None,  # Rockstar doesn't provide this
        "job_id": "job_id",
        "posted_date": None,
        "job_url": "job_url",
        "company": {"field": "company"},  # e.g., "Rockstar North"
    },
    "rebellion": {
        "title": "title",
        "location": {"fields": ["city", "country"], "transform": "join_comma"},
        "other_locations": None,
        "department": "department",
        "work_location_option": {"field": "workplace_type", "transform": "rebellion_work_type"},
        "job_id": "shortcode",
        "posted_date": None,
        "job_url": "job_url",
        "company": {"value": "Rebellion"},
    },
    "miniclip": {
        "title": "title",
        "location": "location",
        "other_locations": None,
        "department": None,  # Miniclip doesn't provide department in listing
        "work_location_option": None,  # Miniclip doesn't provide this
        "job_id": None,  # No explicit ID in listing
        "posted_date": "posted_date",
        "job_url": "job_url",
        "company": {"value": "Miniclip"},
    },
    "google": {
        "title": "title",
        "location": "location",
        "other_locations": None,
        "department": None,  # Google doesn't provide department in listing
        "work_location_option": {"field": "remote_eligible", "transform": "google_remote"},
        "job_id": "job_id",
        "posted_date": None,
        "job_url": "job_url",
        "company": {"value": "Google"},
    },
    "ibm": {
        "title": "title",
        "location": "location",
        "other_locations": None,
        "department": "team",
        "work_location_option": None,  # IBM doesn't provide this in listing
        "job_id": "job_id",
        "posted_date": None,
        "job_url": "job_url",
        "company": {"value": "IBM"},
    },
}

# Rockstar studio locations
ROCKSTAR_LOCATIONS = {
    "Rockstar North": "Edinburgh, UK",
    "Rockstar Leeds": "Leeds, UK",
    "Rockstar Lincoln": "Lincoln, UK",
    "Rockstar London": "London, UK",
    "Rockstar Dundee": "Dundee, UK",
    "Rockstar New York": "New York, USA",
    "Rockstar San Diego": "San Diego, USA",
    "Rockstar Toronto": "Toronto, Canada",
    "Rockstar India": "Bangalore, India",
    "Rockstar New England": "Andover, USA",
}


def _apply_transform(value: Any, transform: str, source_data: dict, primary_location: str = "") -> Any:
    """Apply a transformation to a value."""
    if transform == "list_except_primary":
        # Return all locations except the primary one
        if isinstance(value, list):
            return [loc for loc in value if loc != primary_location]
        return []
    
    elif transform == "first_item":
        # Get first item from a list
        if isinstance(value, list) and value:
            return value[0]
        return ""
    
    elif transform == "lowercase":
        # Convert to lowercase
        if isinstance(value, str):
            return value.lower()
        return ""
    
    elif transform == "strip_posted":
        # Remove "Posted " prefix from Samsung dates
        if isinstance(value, str):
            return value.replace("Posted ", "")
        return ""
    
    elif transform == "rockstar_location":
        # Map Rockstar studio to location
        return ROCKSTAR_LOCATIONS.get(value, value)
    
    elif transform == "join_comma":
        # Join multiple fields with comma (handled separately)
        return value
    
    elif transform == "rebellion_work_type":
        # Map Rebellion work types
        mapping = {
            "hybrid": "hybrid",
            "on_site": "onsite",
            "remote": "remote",
        }
        return mapping.get(value, "")
    
    elif transform == "google_remote":
        # Map Google remote_eligible boolean
        if value is True:
            return "remote"
        elif value is False:
            return "onsite"
        return ""
    
    return value


def normalize_job(scraper_name: str, source_data: Any) -> NormalizedJobListing:
    """Normalize a scraper's job listing to the standard format.
    
    Args:
        scraper_name: Name of the scraper (e.g., "netflix", "google")
        source_data: The scraper's job listing object (dataclass or dict)
    
    Returns:
        NormalizedJobListing with mapped fields
    """
    # Convert dataclass to dict if needed
    if hasattr(source_data, "__dataclass_fields__"):
        source_dict = asdict(source_data)
    elif isinstance(source_data, dict):
        source_dict = source_data
    else:
        raise ValueError(f"source_data must be a dataclass or dict, got {type(source_data)}")
    
    mapping = SCRAPER_MAPPINGS.get(scraper_name.lower())
    if not mapping:
        raise ValueError(f"No mapping found for scraper: {scraper_name}")
    
    result = {}
    
    # First pass: get primary location for list_except_primary transform
    primary_location = ""
    loc_config = mapping.get("location")
    if isinstance(loc_config, str):
        primary_location = source_dict.get(loc_config, "")
    elif isinstance(loc_config, dict):
        if "fields" in loc_config:
            # Join multiple fields
            values = [source_dict.get(f, "") for f in loc_config["fields"]]
            primary_location = ", ".join(v for v in values if v)
        elif "field" in loc_config:
            raw_value = source_dict.get(loc_config["field"], "")
            if "transform" in loc_config:
                primary_location = _apply_transform(raw_value, loc_config["transform"], source_dict)
            else:
                primary_location = raw_value
    
    # Second pass: map all fields
    for standard_field, config in mapping.items():
        if config is None:
            # Field not available from this scraper
            result[standard_field] = [] if standard_field == "other_locations" else ""
        
        elif isinstance(config, str):
            # Direct field mapping
            result[standard_field] = source_dict.get(config, "")
        
        elif isinstance(config, dict):
            if "value" in config:
                # Static value
                result[standard_field] = config["value"]
            
            elif "fields" in config:
                # Multiple fields to join
                values = [source_dict.get(f, "") for f in config["fields"]]
                joined = ", ".join(v for v in values if v)
                if "transform" in config:
                    result[standard_field] = _apply_transform(joined, config["transform"], source_dict, primary_location)
                else:
                    result[standard_field] = joined
            
            elif "field" in config:
                # Single field with optional transform
                raw_value = source_dict.get(config["field"], "")
                if "transform" in config:
                    result[standard_field] = _apply_transform(raw_value, config["transform"], source_dict, primary_location)
                else:
                    result[standard_field] = raw_value
    
    # Ensure other_locations is a list
    if not isinstance(result.get("other_locations"), list):
        result["other_locations"] = []
    
    return NormalizedJobListing(**result)


def normalize_jobs(scraper_name: str, jobs: list) -> list[NormalizedJobListing]:
    """Normalize a list of scraper jobs to standard format.
    
    Args:
        scraper_name: Name of the scraper
        jobs: List of job listings from the scraper
    
    Returns:
        List of NormalizedJobListing objects
    """
    return [normalize_job(scraper_name, job) for job in jobs]


def get_mapping_info(scraper_name: str) -> dict:
    """Get the mapping configuration for a scraper.
    
    Useful for debugging or understanding how fields are mapped.
    """
    mapping = SCRAPER_MAPPINGS.get(scraper_name.lower())
    if not mapping:
        return {"error": f"No mapping found for {scraper_name}"}
    
    info = {
        "scraper": scraper_name,
        "field_mappings": {},
    }
    
    for standard_field, config in mapping.items():
        if config is None:
            info["field_mappings"][standard_field] = "NOT AVAILABLE"
        elif isinstance(config, str):
            info["field_mappings"][standard_field] = f"← {config}"
        elif isinstance(config, dict):
            if "value" in config:
                info["field_mappings"][standard_field] = f"= \"{config['value']}\" (static)"
            elif "fields" in config:
                info["field_mappings"][standard_field] = f"← {' + '.join(config['fields'])}"
                if "transform" in config:
                    info["field_mappings"][standard_field] += f" ({config['transform']})"
            elif "field" in config:
                info["field_mappings"][standard_field] = f"← {config['field']}"
                if "transform" in config:
                    info["field_mappings"][standard_field] += f" ({config['transform']})"
    
    return info


def print_all_mappings():
    """Print mapping info for all scrapers."""
    for scraper_name in SCRAPER_MAPPINGS:
        info = get_mapping_info(scraper_name)
        print(f"\n{'='*60}")
        print(f"{scraper_name.upper()}")
        print("="*60)
        for field, mapping in info["field_mappings"].items():
            print(f"  {field:25} {mapping}")


if __name__ == "__main__":
    print_all_mappings()
