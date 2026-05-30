from datetime import datetime, timedelta
from pathlib import Path


def create_day_posts(start_day, num_posts, start_date=None):
    """
    Creates Jekyll posts with increasing dates and DAY numbers.

    Example:
    2026-05-21-DAY1.md
    2026-05-22-DAY2.md
    2026-05-23-DAY3.md
    """

    # max 10 posts
    num_posts = min(num_posts, 10)

    # use today's date if none provided
    if start_date is None:
        current_date = datetime.today()
    else:
        current_date = datetime.strptime(start_date, "%Y-%m-%d")

    # ensure _posts exists
    posts_dir = Path("_posts")
    posts_dir.mkdir(exist_ok=True)

    for i in range(num_posts):

        day_number = start_day + i

        # increment date
        post_date = current_date + timedelta(days=i)
        date_str = post_date.strftime("%Y-%m-%d")

        # filename
        filename = f"{date_str}-Day{day_number}.md"
        filepath = posts_dir / filename

        # yaml content
        content = f"""---
layout: post
title: Day {day_number}
date: {date_str}
tags: [week5]
---

"""

        # write file
        with open(filepath, "w") as f:
            f.write(content)

        print(f"Created: {filepath}")


# Example usage
create_day_posts(
    start_day=34,
    num_posts=3,
    start_date="2026-05-25"
)