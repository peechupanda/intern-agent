import json
import os

def load_profile(path: str = None) -> dict:
    if path is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "data", "profile.json")
    
    with open(path, "r") as f:
        return json.load(f)

def get_skills(profile: dict) -> list:
    skills = []
    for category, items in profile["skills"].items():
        skills.extend(items)
    return skills

def get_hard_filters(profile: dict) -> list:
    return profile["internship_preferences"]["hard_filters"]

def get_top_tier_companies(profile: dict) -> list:
    return profile["internship_preferences"]["top_tier_companies"]

def summarise_profile(profile: dict) -> str:
    p = profile["personal"]
    skills = get_skills(profile)
    roles = profile["internship_preferences"]["target_roles"]
    achievements = profile["achievements"]

    return f"""
Name: {p['name']}
College: {p['college']} — {p['degree']} (Year 2, CGPA: {p['cgpa']})
Skills: {', '.join(skills)}
Target roles: {', '.join(roles)}
Key achievements: {'; '.join(achievements[:3])}
""".strip()

if __name__ == "__main__":
    profile = load_profile()
    print(summarise_profile(profile))