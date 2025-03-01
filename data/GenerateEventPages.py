import os
import random
from faker import Faker

# Configuration
fake = Faker()
Faker.seed(42)
random.seed(42)

# List of major European cities with at least 2 cities per country
cities = {
    "France": ["Paris", "Lyon"],
    "Germany": ["Berlin", "Munich"],
    "Italy": ["Rome", "Milan"],
    "Spain": ["Madrid", "Barcelona"],
    "United Kingdom": ["London", "Manchester"],
    "Austria": ["Vienna", "Salzburg"],
    "Portugal": ["Lisbon", "Porto"],
    "Netherlands": ["Amsterdam", "Rotterdam"],
    "Belgium": ["Brussels", "Antwerp"],
    "Czech Republic": ["Prague", "Brno"],
    "Sweden": ["Stockholm", "Gothenburg"],
    "Denmark": ["Copenhagen", "Aarhus"],
    "Ireland": ["Dublin", "Cork"],
    "Finland": ["Helsinki", "Tampere"],
    "Norway": ["Oslo", "Bergen"],
    "Greece": ["Athens", "Thessaloniki"],
    "Poland": ["Warsaw", "Krakow"],
    "Hungary": ["Budapest", "Debrecen"],
    "Switzerland": ["Zurich", "Geneva"]
}

# Event categories and adapted descriptions
categories = {
    "Concert": "A unique musical performance featuring renowned artists.",
    "Exhibition": "A fascinating gallery showcasing exclusive works of art.",
    "Theater": "A captivating performance featuring talented actors.",
    "Festival": "A festive event with performances, music, and entertainment.",
    "Dance": "A dance show highlighting the talent of choreographers and dancers.",
    "Conference": "An enriching seminar with domain experts.",
    "Cinema": "A special screening of a film with a discussion in the presence of the directors.",
    "Opera": "A lyrical evening with exceptional vocal performances."
}

# Output directory
output_dir = "events"
os.makedirs(output_dir, exist_ok=True)


# Generating HTML and TXT files
for i in range(1, 101):
    country = random.choice(list(cities.keys()))
    city = random.choice(cities[country])
    category, category_desc = random.choice(list(categories.items()))
    event_name = f"{category} in {city}: {fake.catch_phrase()}"
    event_desc = f"{category_desc} Come and discover '{event_name}', an immersive experience that will transport you." \
                 f" This event will take place in a unique setting in {city}, bringing together enthusiasts and experts." \
                 f" Enjoy an unforgettable and enriching moment."
    event_date = fake.date_between(start_date="-30d", end_date="+90d").strftime("%d %B %Y")
    event_link = f"https://example.com/event_{i}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang='en'>
    <head>
        <meta charset='UTF-8'>
        <meta name='viewport' content='width=device-width, initial-scale=1.0'>
        <title>{event_name}</title>
    </head>
    <body>
        <h1>{event_name}</h1>
        <p><strong>Date:</strong> {event_date}</p>
        <p><strong>City:</strong> {city}</p>
        <p><strong>Category:</strong> {category}</p>
        <p>{event_desc}</p>
        <h2>About this event</h2>
        <p>{fake.paragraph(nb_sentences=8)}</p>
        <p><a href='{event_link}'>More information</a></p>
    </body>
    </html>
    """
    
    text_content = f"""
    {event_name}
    Date: {event_date}
    City: {city}
    Category: {category}
    
    {event_desc}
    
    About this event:
    {fake.paragraph(nb_sentences=8)}
    
    More information: {event_link}
    """
    
    html_file_path = os.path.join(output_dir, f"event_{i}.html")
    txt_file_path = os.path.join(output_dir, f"event_{i}.txt")
    
    with open(html_file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    with open(txt_file_path, "w", encoding="utf-8") as f:
        f.write(text_content)
    
print(f"100 HTML and TXT pages generated in the folder: {output_dir}")
