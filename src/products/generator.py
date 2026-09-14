"""
Generate realistic product listings (name, description, category, price).

Built to make full-text search demos interesting (BM25 / pg_textsearch vs. ILIKE / tsvector):
  - Shared vocabulary across categories ("wireless", "waterproof", "lightweight") so
    queries match many rows and ranking actually matters.
  - Rare long-tail terms ("titanium", "merino", "borosilicate") that get high IDF.
  - Descriptions of varying length (1-7 sentences) to show length normalization.
  - Occasional repeated key terms to show term-frequency saturation.
  - Word-form variety ("run", "running", "runners") to show stemming.

Every name and every description is unique within a run. Stdlib only, deterministic
with --seed, and streamed, so millions of rows are fine.

In Django, use the management command (from src/):
    uv run python manage.py generate_products 50000 --seed 42

Standalone, for CSV / JSON / raw SQL (from src/):
    uv run python products/generator.py --count 100000 --format csv -o products.csv
    uv run python products/generator.py --count 50000 --format sql -o products.sql
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from decimal import Decimal
from itertools import islice
from typing import Iterable, Iterator

BRANDS = [
    "Northwind", "Acme", "Lumen", "Kestrel", "Halcyon", "Ironclad", "Bluebird",
    "Summit", "Vireo", "Obsidian", "Terrafirma", "Cobalt", "Juniper", "Atlas",
    "Monarch", "Pinecrest", "Solstice", "Fathom", "Evergreen", "Quartz", "Nimbus",
    "Redwood", "Aurora", "Basalt", "Harbor & Finch", "Wildgrain", "Copperline",
]

MODEL_SUFFIXES = ["Pro", "Max", "Lite", "Plus", "Mini", "Ultra", "Air", "Elite", "Classic", "Sport", "Studio", "Trail"]
MODEL_CODE_PREFIXES = ["K", "X", "M", "R", "S", "T", "V", "Z", "AX", "MX", "HX", "QS", "LT", "ZR"]


def _model_code(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.7:
        return f"{rng.choice(MODEL_CODE_PREFIXES)}{rng.randint(1, 99) * 10}"
    if roll < 0.85:
        return f"Gen {rng.randint(2, 6)}"
    return f"Series {rng.randint(3, 9)}"


def P(price, features, uses, adjectives, materials=()):
    """Product spec: price range, specific features, use cases, fitting adjectives, materials."""
    return {"price": price, "features": features, "uses": uses, "adjectives": adjectives, "materials": materials}


# Adjectives like "wireless", "lightweight", "durable", "portable" deliberately recur across
# categories (low IDF). Materials like "titanium" or "merino wool" are rarer (high IDF).
CATEGORIES: dict[str, dict] = {
    "Electronics": {
        "audience": ["gamers", "developers", "remote workers", "content creators", "students", "audiophiles"],
        "products": {
            "Mechanical Keyboard": P((49, 329),
                ["hot-swappable switches", "RGB backlighting", "PBT keycaps", "a gasket-mounted design", "USB-C connectivity", "programmable macros"],
                ["gaming", "coding", "typing all day"], ["wireless", "compact", "tenkeyless", "durable"], ["aluminum", "polycarbonate"]),
            "Wireless Mouse": P((19, 149),
                ["a 26,000 DPI sensor", "multi-device pairing", "silent clicks", "a 70-day battery life", "customizable buttons"],
                ["gaming", "productivity", "travel"], ["ergonomic", "lightweight", "rechargeable", "wireless"], ["matte plastic"]),
            "Noise-Cancelling Headphones": P((79, 549),
                ["active noise cancellation", "a 40-hour battery life", "a transparency mode", "spatial audio", "fast charging"],
                ["flights", "focus work", "commuting", "listening to music"], ["wireless", "foldable", "lightweight", "premium"], ["memory foam", "vegan leather"]),
            "Bluetooth Speaker": P((29, 399),
                ["360-degree sound", "an IP67 rating", "deep bass", "a 20-hour battery life", "stereo pairing"],
                ["pool parties", "camping", "the beach", "backyard gatherings"], ["waterproof", "portable", "rugged", "wireless"], ["fabric mesh", "silicone"]),
            "USB-C Hub": P((19, 129),
                ["100W power delivery", "4K HDMI output", "an SD card reader", "gigabit Ethernet", "three USB-A ports"],
                ["laptop setups", "travel", "home offices"], ["compact", "portable", "slim"], ["aluminum"]),
            "4K Monitor": P((229, 1299),
                ["a 144Hz refresh rate", "HDR600 support", "USB-C with 90W charging", "factory color calibration", "a height-adjustable stand"],
                ["photo editing", "gaming", "coding", "video editing"], ["ultrawide", "anti-glare", "premium"], []),
            "Earbuds": P((24, 279),
                ["active noise cancellation", "a wireless charging case", "sweat resistance", "low-latency Bluetooth 5.3", "a secure-fit wing tip"],
                ["running", "workouts", "commuting", "phone calls"], ["wireless", "waterproof", "compact", "lightweight"], []),
            "Power Bank": P((19, 149),
                ["20,000mAh capacity", "65W fast charging", "a built-in USB-C cable", "pass-through charging", "an LED charge display"],
                ["travel", "camping", "long flights"], ["portable", "slim", "rechargeable", "rugged"], ["aluminum"]),
            "Streaming Microphone": P((49, 299),
                ["a cardioid pickup pattern", "zero-latency monitoring", "a built-in pop filter", "a tap-to-mute button", "24-bit/96kHz recording"],
                ["podcasting", "streaming", "voiceovers", "video calls"], ["plug-and-play", "compact", "professional"], ["die-cast metal"]),
            "Smartwatch": P((99, 799),
                ["heart rate monitoring", "built-in GPS", "sleep tracking", "an always-on AMOLED display", "contactless payments"],
                ["marathon training", "hiking", "daily fitness tracking", "sleep improvement"], ["waterproof", "lightweight", "rechargeable"], ["titanium", "sapphire crystal", "stainless steel"]),
        },
    },
    "Furniture": {
        "audience": ["remote workers", "families", "renters", "designers", "students"],
        "products": {
            "Standing Desk": P((249, 1199),
                ["a dual-motor lift system", "four memory presets", "anti-collision detection", "hidden cable management", "a weight capacity of 300 lbs"],
                ["home offices", "better posture", "long workdays"], ["adjustable", "sturdy", "electric", "ergonomic"], ["solid walnut", "bamboo", "steel"]),
            "Office Chair": P((149, 1499),
                ["adjustable lumbar support", "4D armrests", "a synchro-tilt mechanism", "a breathable mesh back", "a headrest"],
                ["long workdays", "home offices", "gaming", "better posture"], ["ergonomic", "adjustable", "breathable"], ["mesh", "full-grain leather", "aluminum"]),
            "Bookshelf": P((69, 699),
                ["five adjustable shelves", "wall anchoring hardware", "a scratch-resistant finish", "tool-free assembly"],
                ["living rooms", "home libraries", "small apartments"], ["modern", "minimalist", "sturdy"], ["solid oak", "walnut veneer", "steel"]),
            "Sectional Sofa": P((699, 3499),
                ["reversible chaise cushions", "stain-resistant performance fabric", "high-resilience foam", "removable washable covers"],
                ["family movie nights", "living rooms", "entertaining guests"], ["modular", "cozy", "pet-friendly"], ["boucle", "velvet", "linen"]),
            "Bed Frame": P((179, 1899),
                ["under-bed storage drawers", "no box spring required", "a padded headboard", "silent wood slats"],
                ["bedrooms", "small apartments", "guest rooms"], ["modern", "sturdy", "low-profile"], ["solid acacia", "upholstered linen", "steel"]),
            "Coffee Table": P((89, 999),
                ["a lift-top surface", "hidden storage", "rounded corners", "a water-resistant finish"],
                ["living rooms", "small spaces", "entertaining guests"], ["mid-century", "minimalist", "compact"], ["travertine", "marble", "reclaimed wood", "tempered glass"]),
            "Floating Shelf": P((19, 129),
                ["concealed mounting brackets", "a 50 lb weight capacity", "a hand-oiled finish"],
                ["kitchens", "bathrooms", "displaying plants"], ["minimalist", "rustic", "compact"], ["solid oak", "walnut", "reclaimed pine"]),
            "Bar Stool": P((59, 399),
                ["a 360-degree swivel", "gas-lift height adjustment", "a built-in footrest", "floor-protecting pads"],
                ["kitchen islands", "home bars", "counter seating"], ["adjustable", "modern", "stackable"], ["rattan", "vegan leather", "powder-coated steel"]),
        },
    },
    "Kitchen": {
        "audience": ["home cooks", "coffee lovers", "bakers", "professional chefs", "busy families"],
        "products": {
            "Chef's Knife": P((29, 349),
                ["a razor-sharp 15-degree edge", "a full tang", "a balanced ergonomic handle", "hand-forged construction"],
                ["meal prep", "slicing vegetables", "breaking down poultry"], ["professional", "durable", "precise"], ["Damascus steel", "VG-10 steel", "high-carbon stainless steel", "olive wood"]),
            "Dutch Oven": P((49, 449),
                ["even heat distribution", "a tight-fitting self-basting lid", "oven-safe construction up to 500°F", "a chip-resistant enamel interior"],
                ["braising", "baking bread", "slow-cooked stews", "weeknight dinners"], ["heavy-duty", "durable", "heirloom-quality"], ["enameled cast iron", "cast iron"]),
            "Nonstick Skillet": P((24, 199),
                ["a PFAS-free nonstick coating", "a stay-cool handle", "induction compatibility", "oven-safe construction"],
                ["cooking eggs", "searing fish", "weeknight dinners"], ["lightweight", "dishwasher-safe", "durable"], ["ceramic-coated aluminum", "tri-ply stainless steel"]),
            "Espresso Machine": P((149, 2499),
                ["a 15-bar pump", "a steam wand for microfoam", "PID temperature control", "a built-in burr grinder", "a pre-infusion mode"],
                ["brewing espresso", "making lattes", "morning routines"], ["compact", "programmable", "premium"], ["brushed stainless steel"]),
            "Pour-Over Kettle": P((29, 189),
                ["a gooseneck spout", "precise temperature control", "a keep-warm setting", "a built-in brew timer"],
                ["pour-over coffee", "brewing tea", "morning routines"], ["electric", "precise", "compact"], ["matte black stainless steel", "copper"]),
            "Air Fryer": P((59, 299),
                ["a 6-quart basket", "eight cooking presets", "a dishwasher-safe basket", "a viewing window", "rapid air circulation"],
                ["crispy fries", "reheating leftovers", "healthy meals", "busy weeknights"], ["compact", "programmable", "energy-efficient"], []),
            "Cutting Board": P((19, 179),
                ["juice grooves", "non-slip feet", "reversible sides", "a knife-friendly surface"],
                ["meal prep", "carving roasts", "charcuterie"], ["durable", "reversible", "extra-large"], ["end-grain walnut", "maple", "bamboo", "teak"]),
            "Burr Coffee Grinder": P((39, 499),
                ["40 grind settings", "conical steel burrs", "a low-retention chute", "a dosing timer"],
                ["espresso", "French press", "pour-over coffee", "cold brew"], ["precise", "quiet", "compact"], ["titanium-coated steel", "aluminum"]),
            "Food Storage Containers": P((19, 89),
                ["airtight snap lids", "stackable nesting design", "microwave-safe bases", "leakproof seals"],
                ["meal prep", "lunches", "pantry organization"], ["reusable", "dishwasher-safe", "eco-friendly"], ["borosilicate glass", "BPA-free plastic", "stainless steel"]),
        },
    },
    "Outdoors": {
        "audience": ["hikers", "campers", "trail runners", "weekend adventurers", "ultralight backpackers"],
        "products": {
            "Hiking Backpack": P((59, 399),
                ["an adjustable torso length", "a ventilated back panel", "an integrated rain cover", "a hydration sleeve", "hip belt pockets"],
                ["day hikes", "backpacking", "thru-hiking", "travel"], ["lightweight", "waterproof", "durable", "ultralight"], ["ripstop nylon", "Dyneema", "recycled polyester"]),
            "Camping Tent": P((89, 899),
                ["a full-coverage rainfly", "sealed seams", "two vestibules", "color-coded poles", "a quick-pitch design"],
                ["car camping", "backpacking", "festival camping"], ["waterproof", "lightweight", "freestanding", "ultralight"], ["silnylon", "aluminum poles", "Dyneema"]),
            "Sleeping Bag": P((49, 599),
                ["a 20°F comfort rating", "a draft collar", "an anti-snag zipper", "a compression stuff sack"],
                ["backpacking", "winter camping", "car camping"], ["lightweight", "packable", "ultralight", "warm"], ["800-fill goose down", "synthetic insulation"]),
            "Trekking Poles": P((29, 219),
                ["flick-lock adjustment", "cork grips", "carbide tips", "shock absorption"],
                ["steep descents", "thru-hiking", "snowshoeing"], ["collapsible", "lightweight", "adjustable"], ["carbon fiber", "aluminum"]),
            "Headlamp": P((19, 129),
                ["a 400-lumen beam", "a red night-vision mode", "a lockout switch", "USB-C charging"],
                ["night hikes", "camping", "trail running", "power outages"], ["rechargeable", "waterproof", "lightweight"], []),
            "Insulated Water Bottle": P((19, 59),
                ["double-wall vacuum insulation", "a leakproof lid", "a powder-coated grip", "a wide mouth for ice cubes"],
                ["hiking", "the gym", "commuting", "road trips"], ["reusable", "durable", "leakproof", "eco-friendly"], ["stainless steel", "titanium"]),
            "Rain Jacket": P((69, 449),
                ["a three-layer waterproof membrane", "pit zips for ventilation", "an adjustable hood", "fully taped seams"],
                ["rainy commutes", "hiking", "travel"], ["waterproof", "breathable", "packable", "lightweight"], ["Gore-Tex", "recycled nylon"]),
            "Trail Running Shoes": P((89, 199),
                ["grippy lugged outsoles", "a rock plate", "a responsive foam midsole", "a gusseted tongue"],
                ["trail running", "fastpacking", "ultramarathons"], ["lightweight", "waterproof", "breathable", "cushioned"], ["Gore-Tex", "engineered mesh"]),
            "Cooler": P((39, 499),
                ["five days of ice retention", "a bear-resistant lid", "a built-in bottle opener", "a drain plug"],
                ["camping", "tailgating", "fishing trips", "beach days"], ["rugged", "portable", "heavy-duty"], ["rotomolded plastic"]),
            "Water Filter": P((19, 119),
                ["0.1-micron hollow fiber filtration", "a squeeze pouch", "backflush cleaning", "a 100,000-gallon lifespan"],
                ["backpacking", "emergency kits", "international travel"], ["lightweight", "portable", "compact"], []),
        },
    },
    "Apparel": {
        "audience": ["runners", "commuters", "minimalists", "athletes", "travelers"],
        "products": {
            "Crewneck Sweater": P((39, 249),
                ["ribbed cuffs", "a relaxed fit", "a naturally odor-resistant knit", "pill-resistant yarn"],
                ["layering", "cold mornings", "the office"], ["cozy", "breathable", "classic"], ["merino wool", "cashmere", "organic cotton"]),
            "Running Shorts": P((19, 79),
                ["a built-in liner", "a zip back pocket", "reflective details", "a 5-inch inseam"],
                ["running", "marathon training", "workouts"], ["lightweight", "quick-dry", "breathable"], ["recycled polyester"]),
            "Base Layer Top": P((29, 129),
                ["flatlock seams", "thumb loops", "moisture-wicking fabric", "odor control"],
                ["skiing", "winter hiking", "layering"], ["lightweight", "breathable", "warm"], ["merino wool", "synthetic blend"]),
            "Denim Jacket": P((49, 229),
                ["reinforced stitching", "a sherpa collar", "button-flap chest pockets"],
                ["everyday wear", "layering", "cool evenings"], ["classic", "durable", "vintage-wash"], ["selvedge denim", "organic cotton"]),
            "Chino Pants": P((39, 149),
                ["four-way stretch", "a tailored fit", "a hidden zip pocket", "wrinkle resistance"],
                ["the office", "travel", "everyday wear"], ["stretch", "classic", "wrinkle-free"], ["organic cotton twill"]),
            "Wool Socks": P((12, 36),
                ["cushioned soles", "arch support", "a seamless toe", "odor control"],
                ["hiking", "running", "cold weather"], ["breathable", "durable", "warm"], ["merino wool", "alpaca"]),
            "Hoodie": P((35, 159),
                ["a brushed fleece interior", "a kangaroo pocket", "a double-lined hood"],
                ["lounging", "layering", "cool evenings"], ["cozy", "oversized", "heavyweight"], ["organic cotton", "recycled fleece"]),
            "Leggings": P((25, 128),
                ["a high-rise waistband", "side pockets", "squat-proof fabric", "four-way stretch"],
                ["yoga", "running", "workouts"], ["breathable", "sculpting", "stretch"], ["recycled nylon"]),
            "Leather Belt": P((29, 149),
                ["a solid brass buckle", "hand-burnished edges", "a stitched keeper"],
                ["the office", "everyday wear", "formal events"], ["classic", "durable", "handmade"], ["full-grain leather", "vegetable-tanned leather"]),
        },
    },
    "Home & Garden": {
        "audience": ["pet owners", "gardeners", "homeowners", "light sleepers", "DIYers"],
        "products": {
            "Robot Vacuum": P((149, 1299),
                ["LiDAR navigation", "a self-emptying base", "app control", "carpet boost suction", "no-go zones"],
                ["pet hair", "busy households", "hardwood floors"], ["smart", "quiet", "cordless"], []),
            "Air Purifier": P((79, 799),
                ["a true HEPA filter", "an activated carbon layer", "an air quality sensor", "whisper-quiet sleep mode"],
                ["allergy relief", "wildfire smoke", "pet dander", "bedrooms"], ["smart", "quiet", "energy-efficient"], []),
            "Smart Thermostat": P((99, 279),
                ["learning schedules", "remote sensors", "voice assistant compatibility", "energy usage reports"],
                ["lowering energy bills", "whole-home comfort"], ["smart", "wireless", "energy-efficient"], []),
            "Ceramic Planter": P((15, 149),
                ["drainage holes", "a matching saucer", "a hand-glazed finish"],
                ["indoor plants", "succulents", "fiddle leaf figs"], ["modern", "minimalist", "handmade"], ["ceramic", "terracotta", "stoneware"]),
            "Garden Hose": P((25, 129),
                ["kink-resistant construction", "brass fittings", "a 10-pattern spray nozzle"],
                ["watering gardens", "washing cars", "patios"], ["lightweight", "expandable", "durable"], ["polyurethane", "natural rubber"]),
            "Weighted Blanket": P((49, 299),
                ["evenly distributed glass beads", "a removable duvet cover", "cooling fabric"],
                ["better sleep", "anxiety relief", "cozy evenings"], ["cooling", "breathable", "cozy"], ["bamboo viscose", "organic cotton", "minky fabric"]),
            "Cordless Drill": P((59, 349),
                ["a brushless motor", "two-speed gearbox", "an LED work light", "a 20V lithium-ion battery"],
                ["DIY projects", "furniture assembly", "home repairs"], ["cordless", "compact", "rechargeable"], []),
            "Raised Garden Bed": P((49, 399),
                ["an open-bottom design", "tool-free assembly", "a weather-resistant finish"],
                ["vegetable gardens", "herb gardens", "small yards"], ["durable", "modular", "rust-resistant"], ["cedarwood", "galvanized steel"]),
            "LED Desk Lamp": P((25, 199),
                ["dimmable warm-to-cool light", "a wireless charging base", "an auto-shutoff timer", "a flicker-free panel"],
                ["late-night reading", "home offices", "studying"], ["adjustable", "energy-efficient", "modern"], ["aluminum", "walnut"]),
        },
    },
    "Sports & Fitness": {
        "audience": ["runners", "cyclists", "yogis", "weightlifters", "beginners"],
        "products": {
            "Yoga Mat": P((19, 149),
                ["a non-slip surface", "alignment lines", "extra cushioning", "a carrying strap"],
                ["yoga", "pilates", "home workouts"], ["non-slip", "eco-friendly", "lightweight"], ["natural rubber", "cork", "TPE"]),
            "Adjustable Dumbbells": P((99, 799),
                ["quick-change weight selection", "5 to 52.5 lb range", "a compact storage tray"],
                ["strength training", "home workouts"], ["adjustable", "space-saving", "durable"], ["cast iron", "steel"]),
            "Resistance Bands": P((12, 59),
                ["five resistance levels", "door anchors", "padded handles"],
                ["physical therapy", "travel workouts", "strength training"], ["portable", "durable", "lightweight"], ["natural latex", "fabric"]),
            "Foam Roller": P((15, 79),
                ["a textured grip surface", "high-density foam", "a hollow core"],
                ["recovery", "muscle soreness", "mobility work"], ["firm", "lightweight", "durable"], ["EVA foam"]),
            "Kettlebell": P((25, 179),
                ["a wide textured handle", "a flat base", "a chip-resistant coating"],
                ["HIIT", "strength training", "home workouts"], ["durable", "heavy-duty"], ["cast iron", "competition steel"]),
            "Rowing Machine": P((299, 2199),
                ["magnetic resistance", "a performance monitor", "a foldable frame", "a padded seat"],
                ["cardio", "full-body workouts", "low-impact training"], ["quiet", "foldable", "compact"], ["aluminum", "ash wood"]),
            "Cycling Helmet": P((49, 299),
                ["MIPS impact protection", "18 ventilation channels", "a rear LED light", "a magnetic buckle"],
                ["road cycling", "mountain biking", "commuting"], ["lightweight", "aerodynamic", "breathable"], ["polycarbonate shell"]),
            "Massage Gun": P((49, 399),
                ["six speed settings", "five interchangeable heads", "a 3-hour battery life"],
                ["recovery", "muscle soreness", "post-run recovery"], ["quiet", "portable", "rechargeable"], []),
            "Jump Rope": P((9, 59),
                ["ball-bearing handles", "an adjustable cable length", "a digital counter"],
                ["cardio", "HIIT", "boxing training"], ["adjustable", "lightweight", "portable"], ["steel cable"]),
        },
    },
    "Beauty & Personal Care": {
        "audience": ["people with sensitive skin", "busy professionals", "travelers", "everyone"],
        "products": {
            "Facial Moisturizer": P((12, 89),
                ["hyaluronic acid", "ceramides", "a lightweight non-greasy finish", "fragrance-free formulas"],
                ["dry skin", "sensitive skin", "daily routines"], ["hypoallergenic", "hydrating", "gentle"], []),
            "Vitamin C Serum": P((15, 99),
                ["15% L-ascorbic acid", "ferulic acid", "a dropper applicator"],
                ["brightening", "dark spots", "morning routines"], ["brightening", "lightweight", "cruelty-free"], []),
            "Electric Toothbrush": P((29, 279),
                ["a 2-minute smart timer", "a pressure sensor", "three brushing modes", "a travel case"],
                ["gum health", "whitening", "travel"], ["rechargeable", "waterproof", "quiet"], []),
            "Hair Dryer": P((39, 499),
                ["ionic technology", "three heat settings", "a cool shot button", "a diffuser attachment"],
                ["frizz control", "curly hair", "fast drying"], ["lightweight", "quiet", "powerful"], ["ceramic", "tourmaline"]),
            "Beard Trimmer": P((24, 149),
                ["self-sharpening blades", "20 length settings", "a precision detailer"],
                ["beard grooming", "travel", "daily touch-ups"], ["cordless", "waterproof", "rechargeable"], ["titanium blades", "stainless steel blades"]),
            "Mineral Sunscreen": P((9, 49),
                ["broad-spectrum SPF 50", "zinc oxide", "a sheer tint", "80 minutes of water resistance"],
                ["sun protection", "beach days", "outdoor sports"], ["reef-safe", "hypoallergenic", "lightweight"], []),
            "Shampoo Bar": P((9, 24),
                ["sulfate-free ingredients", "a rich lather", "plastic-free packaging"],
                ["travel", "color-treated hair", "zero-waste routines"], ["eco-friendly", "gentle", "vegan"], ["argan oil", "shea butter"]),
        },
    },
    "Books & Stationery": {
        "audience": ["students", "artists", "writers", "planners", "designers"],
        "products": {
            "Dot Grid Notebook": P((9, 39),
                ["120gsm acid-free paper", "lay-flat binding", "numbered pages", "an elastic closure"],
                ["journaling", "note-taking", "bullet journaling"], ["durable", "compact", "minimalist"], ["vegan leather cover", "recycled paper"]),
            "Fountain Pen": P((19, 399),
                ["a fine steel nib", "a piston filler", "a refillable converter", "a demonstrator barrel"],
                ["calligraphy", "journaling", "everyday writing"], ["classic", "refillable", "balanced"], ["14k gold nib", "brass", "ebonite", "titanium"]),
            "Weekly Planner": P((14, 59),
                ["undated pages", "monthly spreads", "goal-setting prompts", "a ribbon bookmark"],
                ["planning your week", "habit tracking", "studying"], ["undated", "compact", "durable"], ["linen cover"]),
            "Watercolor Set": P((15, 199),
                ["24 half pans", "archival-quality pigments", "a refillable water brush", "a mixing palette"],
                ["plein air painting", "sketching", "illustration"], ["portable", "compact", "professional"], ["tin case"]),
            "Sketchbook": P((9, 49),
                ["mixed-media paper", "a hardbound cover", "perforated pages"],
                ["sketching", "ink drawing", "urban sketching"], ["portable", "durable", "lay-flat"], ["cotton rag paper"]),
            "Mechanical Pencil": P((5, 49),
                ["a rotating lead mechanism", "a knurled grip", "a retractable tip"],
                ["drafting", "technical drawing", "studying"], ["precise", "durable", "balanced"], ["aluminum", "brass"]),
        },
    },
    "Pet Supplies": {
        "audience": ["dog owners", "cat owners", "pet parents"],
        "products": {
            "Orthopedic Dog Bed": P((39, 299),
                ["a removable washable cover", "a waterproof liner", "bolstered edges", "a non-skid base"],
                ["senior dogs", "large breeds", "joint pain"], ["orthopedic", "washable", "chew-resistant"], ["memory foam"]),
            "Cat Tree": P((39, 349),
                ["sisal rope scratching posts", "a hideaway condo", "a hammock perch"],
                ["indoor cats", "multi-cat homes", "small apartments"], ["sturdy", "modern", "space-saving"], ["sisal", "plush fabric"]),
            "Automatic Pet Feeder": P((39, 199),
                ["a programmable schedule", "portion control", "a backup battery", "app notifications"],
                ["busy pet parents", "weight management", "weekend trips"], ["smart", "programmable", "wireless"], ["stainless steel bowl"]),
            "Dog Harness": P((19, 89),
                ["a no-pull front clip", "padded straps", "reflective trim", "a grab handle"],
                ["long walks", "hiking with dogs", "leash training"], ["adjustable", "breathable", "reflective"], ["ripstop nylon"]),
            "Chew Toy": P((6, 29),
                ["a treat-dispensing chamber", "a textured surface", "a floating design"],
                ["aggressive chewers", "puppies", "boredom busting"], ["durable", "non-toxic", "dishwasher-safe"], ["natural rubber"]),
            "Pet Water Fountain": P((25, 99),
                ["a triple filtration system", "a whisper-quiet pump", "a low-water indicator"],
                ["cats", "hydration", "multi-pet homes"], ["quiet", "dishwasher-safe", "wireless"], ["ceramic", "stainless steel"]),
            "Pet Carrier": P((29, 149),
                ["airline-approved dimensions", "mesh ventilation panels", "a padded shoulder strap"],
                ["air travel", "vet visits", "road trips"], ["collapsible", "lightweight", "breathable"], []),
        },
    },
}

OPENERS = [
    "The {brand} {product} is built for {use}.",
    "Meet the {brand} {product}, designed with {audience} in mind.",
    "This {adj} {product_lower} was made for {use}.",
    "Designed for {audience}, this {product_lower} delivers where it counts.",
    "Whether it's {use} or {use2}, the {brand} {product} has you covered.",
    "Go further with the {adj} {brand} {product}, a favorite for {use}.",
]

# Each body template consumes some number of features, so no feature repeats in a description.
BODY = [
    (1, "You also get {f0}."),
    (2, "It features {f0} and {f1}."),
    (3, "Highlights include {f0}, {f1}, and {f2}."),
    (1, "Thanks to {f0}, it's ideal for {use}."),
    (1, "{F0} sets it apart from other {product_plural}."),
    (0, "Made from {material} for a {adj2} build that lasts."),
    (0, "The {adj2} design is perfect for {audience}."),
    (0, "Customers love it for {use2}, too."),
    (1, "It includes {f0} so you can focus on {use}."),
    (0, "If you're shopping for {adj2} {product_plural} for {use}, start here."),
]

CLOSERS = [
    "Backed by a {warranty} warranty.",
    "Ships free in recyclable packaging.",
    "Available in {color} and {color2}.",
    "A great gift for {audience}.",
    "Rated 4.{rating} stars by thousands of {audience}.",
    "Try it risk-free for 30 days.",
]

COLORS = ["black", "slate gray", "forest green", "navy", "sand", "white", "charcoal", "terracotta", "sage", "midnight blue"]
WARRANTIES = ["1-year", "2-year", "5-year", "lifetime"]
UNCOUNTABLE = ("socks", "shorts", "pants", "leggings", "earbuds", "dumbbells", "bands", "containers", "poles")


def _plural(product: str) -> str:
    noun = product.lower()
    if noun.endswith(UNCOUNTABLE) or noun.endswith("s"):
        return noun
    if noun.endswith(("sh", "ch", "x")):
        return noun + "es"
    if noun.endswith("y") and noun[-2] not in "aeiou":
        return noun[:-1] + "ies"
    return noun + "s"


def _price(rng: random.Random, low: float, high: float) -> Decimal:
    # Log-uniform: most items land toward the cheaper end, a few are premium.
    value = math.exp(rng.uniform(math.log(low), math.log(high)))
    if value < 100:
        cents = rng.choice([".99", ".99", ".95", ".49"])
    else:
        cents = rng.choice([".99", ".00", ".00", ".95"])
    return Decimal(f"{int(value)}{cents}")


def make_product(rng: random.Random) -> dict:
    category = rng.choice(list(CATEGORIES))
    cat = CATEGORIES[category]
    product = rng.choice(list(cat["products"]))
    spec = cat["products"][product]
    brand = rng.choice(BRANDS)

    features = rng.sample(spec["features"], k=len(spec["features"]))
    adjs = rng.sample(spec["adjectives"], k=min(2, len(spec["adjectives"])))
    adjs += adjs[:1] * (2 - len(adjs))
    uses = rng.sample(spec["uses"], k=min(2, len(spec["uses"])))
    uses += uses[:1] * (2 - len(uses))
    material = rng.choice(spec["materials"]) if spec["materials"] else None
    colors = rng.sample(COLORS, k=2)

    # Name: brand + optional adjective or material + product + optional model suffix
    name_parts = [brand]
    roll = rng.random()
    if material and roll < 0.25:
        name_parts.append(material.title() if material.islower() else material)
    elif roll < 0.6:
        name_parts.append(adjs[0].title())
    name_parts.append(product)
    if rng.random() < 0.4:
        name_parts.append(rng.choice(MODEL_SUFFIXES))
    if rng.random() < 0.8:
        name_parts.append(_model_code(rng))
    name = " ".join(name_parts)

    ctx = {
        "brand": brand,
        "product": product,
        "product_lower": product.lower(),
        "product_plural": _plural(product),
        "adj": adjs[0],
        "adj2": adjs[1],
        "use": uses[0],
        "use2": uses[1],
        "audience": rng.choice(cat["audience"]),
        "material": material,
        "color": colors[0],
        "color2": colors[1],
        "warranty": rng.choice(WARRANTIES),
        "rating": rng.randint(3, 9),
    }

    # Varying description length exercises BM25 length normalization.
    sentences = [rng.choice(OPENERS).format(**ctx)]
    target = rng.choices([0, 1, 2, 3, 4, 5], weights=[5, 25, 30, 20, 12, 8])[0]
    for needed, template in rng.sample(BODY, k=len(BODY)):
        if len(sentences) > target:
            break
        if needed > len(features) or ("{material}" in template and not material):
            continue
        taken, features = features[:needed], features[needed:]
        fx = {f"f{i}": f for i, f in enumerate(taken)}
        if taken:
            fx["F0"] = taken[0][0].upper() + taken[0][1:]
        sentences.append(template.format(**ctx, **fx))
    if rng.random() < 0.7:
        sentences.append(rng.choice(CLOSERS).format(**ctx))

    # Occasionally repeat the product term to exercise term-frequency saturation.
    if rng.random() < 0.08:
        sentences.append(f"Once you try this {product.lower()}, you won't want any other {product.lower()}.")

    return {
        "name": name,
        "description": " ".join(sentences),
        "category": category,
        "price": _price(rng, *spec["price"]),
    }


def iter_products(
    count: int,
    seed: int | str | None = None,
    exclude_names: Iterable[str] = (),
    exclude_descriptions: Iterable[str] = (),
) -> Iterator[dict]:
    """
    Yield `count` products with unique names and unique descriptions.

    Pass existing names/descriptions (e.g. from the database) to avoid colliding with them.
    Only hashes are kept in memory, so this stays cheap for millions of rows.
    """
    rng = random.Random(seed)
    seen_names = {hash(n) for n in exclude_names}
    seen_descriptions = {hash(d) for d in exclude_descriptions}
    for _ in range(count):
        for _attempt in range(1000):
            product = make_product(rng)
            name_key, desc_key = hash(product["name"]), hash(product["description"])
            if name_key not in seen_names and desc_key not in seen_descriptions:
                break
        else:
            raise RuntimeError("Could not generate a unique product after 1000 attempts; the name space is exhausted.")
        seen_names.add(name_key)
        seen_descriptions.add(desc_key)
        yield product


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", "--count", type=int, default=1000, help="number of products (default: 1000)")
    parser.add_argument("-s", "--seed", type=int, default=None, help="random seed for reproducible output")
    parser.add_argument("-f", "--format", choices=["jsonl", "json", "csv", "sql"], default="jsonl")
    parser.add_argument("-o", "--output", default="-", help="output file (default: stdout)")
    args = parser.parse_args()

    out = sys.stdout if args.output == "-" else open(args.output, "w", newline="", encoding="utf-8")
    products = iter_products(args.count, args.seed)

    try:
        if args.format == "jsonl":
            for p in products:
                out.write(json.dumps(p, default=str) + "\n")
        elif args.format == "json":
            json.dump(list(products), out, default=str, indent=2)
            out.write("\n")
        elif args.format == "csv":
            writer = csv.DictWriter(out, fieldnames=["name", "description", "category", "price"])
            writer.writeheader()
            writer.writerows(products)
        elif args.format == "sql":
            def q(s: str) -> str:
                return "'" + s.replace("'", "''") + "'"

            while batch := list(islice(products, 1000)):
                out.write("INSERT INTO products (name, description, category, price) VALUES\n")
                out.write(",\n".join(
                    f"({q(p['name'])}, {q(p['description'])}, {q(p['category'])}, {p['price']})" for p in batch
                ))
                out.write(";\n")
    finally:
        if out is not sys.stdout:
            out.close()


if __name__ == "__main__":
    main()
