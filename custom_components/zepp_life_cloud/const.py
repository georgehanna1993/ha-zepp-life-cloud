"""Constants for the unofficial Zepp Life cloud integration."""
DOMAIN = "zepp_life_cloud"
DEFAULT_INTERVAL = 60
METRICS = (
    ("weight", "Measurement · Weight", "kg"),
    ("bmi", "Measurement · BMI", None),
    ("fatRate", "Composition · Body fat", "%"),
    ("bodyWaterRate", "Composition · Body water", "%"),
    ("muscleRate", "Composition · Muscle mass", "kg"),
    ("boneMass", "Composition · Bone mass", "kg"),
    ("proteinRatio", "Composition · Protein", "%"),
    ("visceralFat", "Composition · Visceral fat", None),
    ("metabolism", "Metabolism · Basal metabolic rate", "kcal/d"),
    ("muscleAge", "Composition · Body age", "years"),
    ("bodyScore", "Composition · Body score", None),
    ("bodyStyle", "Composition · Body type", None),
    ("standBodyWeight", "Reference · Standard body weight", "kg"),
    ("impedance", "Composition · Impedance", "Ω"),
    ("height", "Reference · Height", "cm"),
    ("bodyBalanceScore", "Composition · Balance score", None),
)
