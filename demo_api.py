import sys
sys.stdout.reconfigure(encoding='utf-8')

from linkedin_api import Linkedin
from config import LINKEDIN_EMAIL, LINKEDIN_PASSWORD

print("מתחבר ל-LinkedIn API...")
api = Linkedin(LINKEDIN_EMAIL, LINKEDIN_PASSWORD)

# בדיקה על פרופיל אחד
profile_id = "moria-david-1b401216a"
print(f"שולף contact info של: {profile_id}\n")

info = api.get_profile_contact_info(profile_id)
print("תוצאה:")
for key, val in info.items():
    if val:
        print(f"  {key}: {val}")
