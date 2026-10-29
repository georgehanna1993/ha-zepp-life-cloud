"""Constants for the unofficial Zepp Life cloud integration."""
DOMAIN = "zepp_life_cloud"
DEFAULT_INTERVAL = 60
METRICS = (
    ("weight", "Weight", "kg"),
    ("bmi", "BMI", None),
    ("fatRate", "Body fat", "%"),
    ("bodyWaterRate", "Body water", "%"),
    ("muscleRate", "Muscle mass", "kg"),
    ("boneMass", "Bone mass", "kg"),
    ("proteinRatio", "Protein", "%"),
    ("visceralFat", "Visceral fat index", None),
    ("metabolism", "Basal metabolism", "kcal/d"),
    ("muscleAge", "Body age", "years"),
    ("bodyScore", "Body score", None),
    ("bodyStyle", "Body type code", None),
    ("standBodyWeight", "Standard body weight", "kg"),
    ("impedance", "Impedance", "Ω"),
    ("height", "Height", "cm"),
    ("bodyBalanceScore", "Balance score", None),
    ("oneFootMeasureTime", "One foot balance time", "s"),
)
