"""Every safety, medical and preparation sentence the app shows. Fixed strings, reviewed once.

Nothing here is generated. The chat quotes these through get_prep. Sources for the numbers:
FDA/USDA food safety (4 h fridge, 48 h full freezer, 40 F / 2 h), CDC generator guidance
(20 ft, CO alarm), Red Cross (1 gallon of water per person per day), FDA insulin storage
(59-86 F, up to 28 days, varies by brand).
"""

EMERGENCY_LINE = ("If you see a downed power line, a fire, or someone is hurt, call 911. "
                  "Stay at least 35 feet away from downed lines.")

SAFETY = [
    {"id": "s_downed_line", "text": ("Treat every downed line as live. Stay at least 35 feet away and keep others away. "
                                     "If a line falls on your car, stay inside unless the car is on fire.")},
    {"id": "s_generator", "text": ("Run generators outdoors only, at least 20 feet from the house, exhaust pointed away "
                                   "from doors and windows. Never in a garage or basement. Never plug one into a wall "
                                   "outlet. Use a battery-powered carbon monoxide alarm. If it sounds or you feel dizzy or sick, "
                                   "get to fresh air and call 911.")},
    {"id": "s_heat", "text": ("Never heat your home with a gas oven, stove, or grill. Use space heaters only if they "
                              "are made for indoor use, keep them 3 feet from anything that can burn, and never "
                              "leave them on unattended.")},
    {"id": "s_candles", "text": "Use flashlights instead of candles. If you must use a candle, never leave it alone."},
]

# Actions by duration bucket. "when": before (storm not here / power on), now (power out), after (restored).
BEFORE = {
    "<4h": [
        {"id": "a_charge", "text": "Charge your phone and any power banks."},
        {"id": "a_light", "text": "Put a flashlight where you can find it in the dark."},
        {"id": "a_alerts", "text": "Keep outage alerts on so we can tell you what's happening."},
    ],
    "4-24h": [
        {"id": "a_charge", "text": "Charge your phone, power banks, and any device batteries now."},
        {"id": "a_light", "text": "Find flashlights and fresh batteries."},
        {"id": "a_fridge_cold", "text": "Turn your fridge and freezer to their coldest settings."},
        {"id": "a_food_ready", "text": "Have a day of food that needs no cooking or refrigeration."},
        {"id": "a_alerts", "text": "Keep outage alerts on so we can tell you what's happening."},
    ],
    "24-72h": [
        {"id": "a_charge", "text": "Charge your phone, power banks, and any device batteries now."},
        {"id": "a_light", "text": "Find flashlights and fresh batteries."},
        {"id": "a_water", "text": "Store drinking water: about 1 gallon per person per day, for 3 days."},
        {"id": "a_food_ready", "text": "Have 3 days of food that needs no cooking or refrigeration."},
        {"id": "a_fridge_cold", "text": "Turn your fridge and freezer to their coldest settings. Freeze containers of water to help keep food cold."},
        {"id": "a_warm", "text": "Gather warm layers and blankets. Plan where you could go to stay warm."},
        {"id": "a_gas_cash", "text": "Fill your car's gas tank and keep some cash; card readers may not work."},
        {"id": "a_neighbors", "text": "Check on neighbors who may need help."},
    ],
    "72h+": [
        {"id": "a_charge", "text": "Charge your phone, power banks, and any device batteries now."},
        {"id": "a_water", "text": "Store drinking water: about 1 gallon per person per day, for several days."},
        {"id": "a_food_ready", "text": "Have several days of food that needs no cooking or refrigeration."},
        {"id": "a_stay_plan", "text": "Plan where you could stay if the outage lasts several days, like a friend or family member with power."},
        {"id": "a_meds_supply", "text": "Make sure you have enough of any medicine you take."},
        {"id": "a_gas_cash", "text": "Fill your car's gas tank and keep some cash; card readers may not work."},
    ],
}

DURING = {
    "<4h": [
        {"id": "a_fridge", "text": ("Keep the fridge and freezer closed. Food stays cold about 4 hours in the fridge, "
                                    "48 hours in a full freezer (24 hours if half full).")},
        {"id": "a_phone", "text": "Turn on your phone's low-power mode to save battery."},
        {"id": "a_unplug", "text": "Unplug electronics so they aren't damaged when power returns."},
    ],
    "4-24h": [
        {"id": "a_fridge", "text": ("Keep the fridge and freezer closed. Food stays cold about 4 hours in the fridge, "
                                    "48 hours in a full freezer (24 hours if half full). Throw out perishable food "
                                    "that has been above 40°F for 2 hours or more.")},
        {"id": "a_phone", "text": ("Turn on your phone's low-power mode. Charge from a power bank, or in a car only "
                                   "when it's outdoors, never in a garage.")},
        {"id": "a_unplug", "text": "Unplug electronics so they aren't damaged when power returns."},
        {"id": "a_warm", "text": "Dress in layers and close off rooms you aren't using to hold in heat."},
    ],
    "24-72h": [
        {"id": "a_fridge", "text": ("Keep the fridge and freezer closed. Food stays cold about 4 hours in the fridge, "
                                    "48 hours in a full freezer (24 hours if half full). Throw out perishable food "
                                    "that has been above 40°F for 2 hours or more.")},
        {"id": "a_phone", "text": ("Turn on your phone's low-power mode. Charge from a power bank, or in a car only "
                                   "when it's outdoors, never in a garage.")},
        {"id": "a_warm_place", "text": "If your home gets too cold, go to a warming center or a home with power."},
        {"id": "a_pipes", "text": "Let a faucet drip to help keep pipes from freezing."},
        {"id": "a_unplug", "text": "Unplug electronics so they aren't damaged when power returns."},
        {"id": "a_neighbors", "text": "Check on neighbors who may need help."},
    ],
    "72h+": [
        {"id": "a_stay", "text": "Consider staying with friends, family, or at a shelter with power."},
        {"id": "a_fridge", "text": ("Keep the freezer closed as long as you can. Throw out perishable food that has "
                                    "been above 40°F for 2 hours or more.")},
        {"id": "a_phone", "text": "Turn on your phone's low-power mode and charge whenever you can."},
        {"id": "a_meds_refill", "text": "If you will run out of medicine, ask a pharmacy about an emergency refill."},
        {"id": "a_pipes", "text": "Let a faucet drip to help keep pipes from freezing."},
    ],
}

AFTER = [
    {"id": "a_food_check", "text": ("Check your food. Throw out perishable food that was above 40°F for 2 hours "
                                    "or more. When in doubt, throw it out.")},
    {"id": "a_plug_back", "text": "Plug electronics back in one at a time."},
    {"id": "a_reset", "text": "Reset clocks, alarms, and your thermostat."},
    {"id": "a_restock", "text": "Restock flashlight batteries and water for next time."},
]

# Declared needs (user toggles only; never inferred, never stored). phase: before | during | after
NEEDS = {
    "medical_device": {
        "before": ("Charge your medical device's backup batteries now and keep your provider's number handy. "
                   "If the device can't run for the expected outage, plan to go somewhere with power early."),
        "during": ("Switch your medical device to backup power. If it can't last until power is back, go somewhere "
                   "with power now. If you feel unwell, call 911."),
        "after": "Check that your medical device is charging and working normally.",
    },
    "refrigerated_meds": {
        "before": ("Keep refrigerated medicine in the fridge. Many insulins are OK at room temperature "
                   "(59-86°F) for up to 28 days, but it varies by brand, so check the label or ask your "
                   "pharmacist. Have a cooler ready."),
        "during": ("Keep insulin in its box, away from heat and from freezing. Many insulins are OK at room "
                   "temperature (59-86°F) for up to 28 days, but it varies by brand, so check the label or ask "
                   "your pharmacist. If you use a cooler, don't let insulin touch ice. Don't use insulin that has frozen."),
        "after": ("Check your medicine. If it got too warm or froze, ask your pharmacist whether it is still "
                  "safe to use before you take it."),
    },
    "mobility": {
        "before": ("Keep a flashlight, phone, and charger within reach. Elevators and lift chairs stop without "
                   "power, so plan another way out or ask someone to check on you."),
        "during": ("Stay where you can reach your phone and a flashlight. Ask a neighbor, friend, or family "
                   "member to check on you."),
        "after": "Check that any powered mobility equipment is charging.",
    },
    "well_water": {
        "before": ("Your well pump needs power. Fill containers with drinking water (about 1 gallon per person "
                   "per day) and fill a bathtub for flushing."),
        "during": "Your well pump won't run without power. Use the water you stored.",
        "after": "Run your taps for a few minutes. If the water looks or smells wrong, don't drink it.",
    },
    "critical_facility": {
        "before": ("Test your backup generator and confirm fuel. Follow your facility's emergency plan and "
                   "make sure the utility has your facility listed as critical."),
        "during": ("Run your facility's emergency plan and backup power. If people in your care are at risk, "
                   "call 911."),
        "after": "Bring systems back slowly and check refrigerated supplies before use.",
    },
}
NEED_KEYS = tuple(NEEDS)
