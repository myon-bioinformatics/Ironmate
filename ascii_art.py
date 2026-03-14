"""
ascii_art.py
Provides functions to generate ASCII art dynamically (square, triangle, diamond)
and retrieve pre-defined ASCII art templates.
"""

# Pre-defined ASCII art templates
TEMPLATES = {
    "ironmate": r"""
  _____                                _
 |_   _|  _ __    ___    _ __   _ __  | |__    __ _   ___   ___
   | |   | '__|  / _ \  | '_ \ | '_ \ | '_ \  / _` | / __| / __|
   | |   | |    | (_) | | | | || | | || | | || (_| || (__ | (__
   |_|   |_|     \___/  |_| |_||_| |_||_| |_| \__,_| \___| \___|
  IRONMATE - Your J.A.R.V.I.S-inspired assistant
""",
    "arc_reactor": r"""
      .---.
    /       \
   |  o   o  |
   |    ^    |
    \  \_/  /
      '---'
  [ ARC REACTOR ]
""",
    "helmet": r"""
   _______
  /       \
 | () | () |
 |   ___   |
  \_______/
  [ IRONMATE ]
""",
    "welcome": r"""
 __        __   _                                
 \ \      / /__| | ___ ___  _ __ ___   ___  
  \ \ /\ / / _ \ |/ __/ _ \| '_ ` _ \ / _ \ 
   \ V  V /  __/ | (_| (_) | | | | | |  __/ 
    \_/\_/ \___|_|\___\___/|_| |_| |_|\___| 
  to IRONMATE!
""",
}


def generate_square(size: int, char: str = "*") -> str:
    """Generate a square of the given size using the specified character.

    Args:
        size: The number of characters per side.
        char: The character to use for drawing (default: '*').

    Returns:
        A string representing a square in ASCII art.
    """
    if size <= 0:
        return ""
    row = char * size
    return "\n".join([row] * size)


def generate_triangle(height: int, char: str = "*") -> str:
    """Generate a right-aligned triangle of the given height.

    Args:
        height: The number of rows in the triangle.
        char: The character to use for drawing (default: '*').

    Returns:
        A string representing a triangle in ASCII art.
    """
    if height <= 0:
        return ""
    lines = []
    for i in range(1, height + 1):
        lines.append(char * i)
    return "\n".join(lines)


def generate_diamond(half_height: int, char: str = "*") -> str:
    """Generate a diamond shape of the given half-height.

    Args:
        half_height: The number of rows from the center to the top (or bottom).
        char: The character to use for drawing (default: '*').

    Returns:
        A string representing a diamond in ASCII art.
    """
    if half_height <= 0:
        return ""
    lines = []
    width = 2 * half_height - 1
    # Upper half (including the middle row)
    for i in range(1, half_height + 1):
        num_chars = 2 * i - 1
        padding = (width - num_chars) // 2
        lines.append(" " * padding + char * num_chars)
    # Lower half
    for i in range(half_height - 1, 0, -1):
        num_chars = 2 * i - 1
        padding = (width - num_chars) // 2
        lines.append(" " * padding + char * num_chars)
    return "\n".join(lines)


def get_template(name: str) -> str:
    """Retrieve a pre-defined ASCII art template by name.

    Args:
        name: The name of the template to retrieve.

    Returns:
        The ASCII art string for the given template name, or an empty string
        if the template is not found.
    """
    return TEMPLATES.get(name, "")


def list_templates() -> list:
    """Return a list of all available template names.

    Returns:
        A list of template name strings.
    """
    return list(TEMPLATES.keys())
