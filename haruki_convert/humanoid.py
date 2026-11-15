"""Unity Humanoid curve names, in the order of the Animator (typeID 95) binding attribute index (137 curves)."""
SIDES = ("Left", "Right")


def muscle_curve_names():
    body = ["Spine Front-Back", "Spine Left-Right", "Spine Twist Left-Right", "Chest Front-Back", "Chest Left-Right",
            "Chest Twist Left-Right", "UpperChest Front-Back", "UpperChest Left-Right", "UpperChest Twist Left-Right",
            "Neck Nod Down-Up", "Neck Tilt Left-Right", "Neck Turn Left-Right", "Head Nod Down-Up", "Head Tilt Left-Right",
            "Head Turn Left-Right", "Left Eye Down-Up", "Left Eye In-Out", "Right Eye Down-Up", "Right Eye In-Out",
            "Jaw Close", "Jaw Left-Right"]
    for s in SIDES:
        body += [f"{s} Upper Leg Front-Back", f"{s} Upper Leg In-Out", f"{s} Upper Leg Twist In-Out", f"{s} Lower Leg Stretch",
                 f"{s} Lower Leg Twist In-Out", f"{s} Foot Up-Down", f"{s} Foot Twist In-Out", f"{s} Toes Up-Down"]
    for s in SIDES:
        body += [f"{s} Shoulder Down-Up", f"{s} Shoulder Front-Back", f"{s} Arm Down-Up", f"{s} Arm Front-Back",
                 f"{s} Arm Twist In-Out", f"{s} Forearm Stretch", f"{s} Forearm Twist In-Out", f"{s} Hand Down-Up", f"{s} Hand In-Out"]
    fingers = [f"{s}Hand.{f}.{k}" for s in SIDES for f in ("Thumb", "Index", "Middle", "Ring", "Little")
               for k in ("1 Stretched", "Spread", "2 Stretched", "3 Stretched")]
    return body + fingers


def curve_names():
    names = [f"MotionT.{a}" for a in "xyz"] + [f"MotionQ.{a}" for a in "xyzw"] + [f"RootT.{a}" for a in "xyz"] + [f"RootQ.{a}" for a in "xyzw"]
    for g in ("LeftFoot", "RightFoot", "LeftHand", "RightHand"):
        names += [f"{g}T.{a}" for a in "xyz"] + [f"{g}Q.{a}" for a in "xyzw"]
    return names + muscle_curve_names()
