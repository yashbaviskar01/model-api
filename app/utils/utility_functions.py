import os
import re
import jwt
import json
from datetime import datetime, timezone
from typing import Any, Dict
from dotenv import load_dotenv
from fastapi import Header

load_dotenv()


class Utils:
    def __init__(self):
        pass

    def convert_to_tz(self, datetime_str, format_str=None):
        formats_to_try = [
            "%Y-%m-%d",  # ISO 8601 format
            "%d-%m-%Y",  # dd-mm-yyyy format
            "%m/%d/%Y",  # mm/dd/yyyy format
            "%d/%m/%Y",  # dd/mm/yyyy format
            "%Y/%m/%d",  # yyyy/mm/dd format
            "%Y.%m.%d",  # yyyy.mm.dd format
            "%Y %m %d",  # yyyy mm dd format
            "%Y%m%d",  # yyyymmdd format
            "%a, %d %b %Y %H:%M:%S %z",  # Fri, 26 Apr 2024 12:00:00 +0000
            "%a, %d %b %Y %H:%M:%S %Z",  # Tue, 30 Apr 2024 08:04:00 GMT
            "%a, %d %b %Y %H:%M:%S %z",  # Mon, 22 Apr 2024 15:00:00 -0000
            "%Y-%m-%dT%H:%M:%S%z",  # 2024-04-04T16:34:21+00:00 format
            "%Y-%m-%dT%H:%M:%S.%fZ",  # 2022-04-29T05:55:26.677Z format
            "%d %b %Y",  # 30 Apr 2023 format
            "%b %d %Y",  # Apr 30 2023 format
            "%Y %d %b",  # 2023 30 Apr format
            "%d %b %y",  # 20 Jan 24 format
            "%d %b",  # 20 Jan
            "%Y-%m-%d %H:%M:%S.%f",  # 2024-07-18 17:55:36.250570 format
        ]

        if format_str != None:
            for format_string in formats_to_try:
                try:
                    date_obj = datetime.strptime(datetime_str, format_string)
                    if date_obj.year == 1900:
                        date_obj = date_obj.replace(year=datetime.now().year)
                    if not date_obj.tzinfo:
                        # Assume the datetime string is in UTC if no timezone info is provided
                        date_obj = date_obj.replace(tzinfo=timezone.utc)
                    else:
                        date_obj = date_obj.astimezone(timezone.utc)
                    formatted_time = date_obj.isoformat(
                        timespec="milliseconds"
                    ).replace("+00:00", "Z")
                    return formatted_time
                except ValueError:
                    pass
        else:
            try:
                formatted_time = datetime.strptime(datetime_str, format_str)
            except Exception as e:
                return e

        raise ValueError("Invalid datetime format")

    def clean_response(self, text):
        keywords = [
            "Message:",
            "Answer:",
            "\\",
            '"',
            "?",
            "System:",
            "```markdown",
            "```",
        ]
        for keyword in keywords:
            text = text.replace(keyword, "")
        text = text.replace("\n", " ")
        text = " ".join(text.split())
        return text

    def get_base_url(self, api_endpoint):
        env = os.getenv("dev")
        base_url = env
        if not base_url:
            raise ValueError(f"Base URL not found for environment: {env}")
        return base_url + api_endpoint

    def clean_markdown(self, md_text):
        # Remove headings (e.g., ## Title)
        md_text = re.sub(r"#+\s+", "", md_text)

        # Remove table dividers and formatting (| --- |)
        md_text = re.sub(r"\|\s*-+\s*\|.*", "", md_text)

        # Convert Markdown links [text](url) → text: url
        md_text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r"\1: \2", md_text)

        # Remove inline formatting (**bold**, *italics*)
        md_text = re.sub(r"\*\*(.*?)\*\*", r"\1", md_text)
        md_text = re.sub(r"\*(.*?)\*", r"\1", md_text)

        # Remove HTML tags (e.g., <br/>)
        md_text = re.sub(r"<[^>]+>", "", md_text)

        # Remove excessive whitespace
        md_text = re.sub(r"\n{2,}", "\n", md_text).strip()

        return md_text



