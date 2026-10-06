"""Every fixed list of values in one place. The schema's CHECK constraints, the
input models and the dashboard (through /api/meta) all read from here."""

WORK_MODES = ("onsite", "hybrid", "remote", "unknown")
EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "internship", "temporary", "unknown")
SENIORITIES = ("intern", "entry", "junior", "mid", "senior", "lead", "unknown")
TRI_STATE = ("yes", "no", "unknown")          # visa sponsorship, relocation
SALARY_PERIODS = ("year", "month", "hour")
APPLY_METHODS = ("email", "form", "link", "referral", "unknown")
SOURCES = ("linkedin", "aijobsuae", "career_services", "referral", "company_site",
           "job_board", "email", "other")
POSTING_STATUSES = ("open", "closed")

# One record per job, and its status says where the pursuit stands:
#   before applying:  new -> shortlisted (or passed)
#   in progress:      drafting -> applied -> screening -> interviewing -> offer
#   closed:           one of the outcomes below
# stage_reached keeps the furthest in-progress stage, so the funnel stays honest after a job closes.
BEFORE = ("new", "shortlisted", "passed")
STAGES = ("drafting", "applied", "screening", "interviewing", "offer")
OUTCOMES = ("accepted", "rejected", "role_filled", "no_response", "withdrew", "declined")
STATUSES = ("new", "shortlisted") + STAGES + OUTCOMES + ("passed",)
PASS_REASONS = ("nationality_restricted", "too_senior", "skills_mismatch", "no_visa",
                "location", "role_type", "not_interested", "posting_closed", "duplicate", "other")
OUTCOME_SIDE = {                   # who ended it, the Greenhouse split
    "accepted": "me", "withdrew": "me", "declined": "me",
    "rejected": "them", "role_filled": "them", "no_response": "them",
}
CHANNELS = ("email", "form", "referral", "in_person", "other")

INTERVIEW_KINDS = ("screen", "technical", "take_home", "onsite", "final", "other")
DRAFT_KINDS = ("application", "follow_up", "thank_you", "other")
DRAFT_STATUSES = ("draft", "in_gmail", "sent", "discarded")
FILE_ENTITIES = ("job", "company")
FILE_KINDS = ("screenshot", "posting", "sent_email", "document", "other")
ACTORS = ("me", "claude", "system", "import")

LABELS = {
    "onsite": "On-site", "hybrid": "Hybrid", "remote": "Remote", "unknown": "Unknown",
    "full_time": "Full-time", "part_time": "Part-time", "contract": "Contract",
    "internship": "Internship", "temporary": "Temporary",
    "intern": "Intern", "entry": "Entry", "junior": "Junior", "mid": "Mid",
    "senior": "Senior", "lead": "Lead",
    "linkedin": "LinkedIn", "aijobsuae": "aijobsuae.ae", "career_services": "Career Services",
    "referral": "Referral", "company_site": "Company site", "job_board": "Job board",
    "email": "Email", "other": "Other",
    "new": "New", "shortlisted": "Shortlisted", "passed": "Passed",
    "nationality_restricted": "Nationality restricted", "too_senior": "Too senior",
    "skills_mismatch": "Skills mismatch", "no_visa": "No visa sponsorship",
    "location": "Location", "role_type": "Wrong kind of role",
    "not_interested": "Not interested", "posting_closed": "Posting closed",
    "duplicate": "Duplicate",
    "drafting": "Drafting", "applied": "Applied", "screening": "Screening",
    "interviewing": "Interviewing", "offer": "Offer",
    "accepted": "Accepted", "rejected": "Rejected", "role_filled": "Role filled",
    "no_response": "No response", "withdrew": "Withdrew", "declined": "Declined offer",
    "form": "Form", "in_person": "In person",
}


def check(column, values, nullable=False):
    allowed = ", ".join(f"'{v}'" for v in values)
    clause = f"{column} IN ({allowed})"
    return f"CHECK ({clause} OR {column} IS NULL)" if nullable else f"CHECK ({clause})"
