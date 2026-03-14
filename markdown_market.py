"""
markdown_market.py
Handles operations related to Markdown files:
- Saving Markdown content to a file
- Reading Markdown files with optional hashtag counting
- Extracting section names (headings) from Markdown content
"""

import os
import re


def save_markdown(content: str, filepath: str) -> str:
    """Save Markdown content to a file.

    Args:
        content: The Markdown content to save.
        filepath: The path to the file where content will be saved.

    Returns:
        A message indicating success or describing an error.
    """
    try:
        dirpath = os.path.dirname(filepath)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Saved successfully: {filepath}"
    except OSError as e:
        return f"Error saving file: {e}"


def read_markdown(filepath: str, count_hashtags: bool = False) -> dict:
    """Read a Markdown file and optionally count hashtags.

    Args:
        filepath: The path to the Markdown file to read.
        count_hashtags: If True, count the number of '#' characters used as
                        heading markers (only leading '#' sequences per line).

    Returns:
        A dictionary with:
            - "content" (str): The file content, or an error message.
            - "hashtag_count" (int | None): Total count of leading '#' characters
              across all heading lines, or None if count_hashtags is False.
            - "success" (bool): True if the file was read successfully.
    """
    result = {"content": "", "hashtag_count": None, "success": False}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        result["content"] = content
        result["success"] = True
        if count_hashtags:
            total = 0
            for line in content.splitlines():
                match = re.match(r"^(#+)", line)
                if match:
                    total += len(match.group(1))
            result["hashtag_count"] = total
    except OSError as e:
        result["content"] = f"Error reading file: {e}"
    return result


def extract_sections(content: str) -> list:
    """Extract section names (Markdown headings) from content.

    Args:
        content: A string containing Markdown content.

    Returns:
        A list of dictionaries, each with:
            - "level" (int): Heading level (1 for H1, 2 for H2, etc.).
            - "title" (str): The heading text without leading '#' characters.
    """
    sections = []
    for line in content.splitlines():
        match = re.match(r"^(#{1,6})\s+(.*)", line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            sections.append({"level": level, "title": title})
    return sections
