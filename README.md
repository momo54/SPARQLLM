Requires RDFLIB 7, OpenAI and python3. 
```
pip install rdflib
pip install openai
```
suppose your chatGPT api key available in os.environ.get("OPENAI_API_KEY")

just run:
```
python main.py
```

SPARQLLM is a way to integrate LLM calls into a SPARQL service. For example, the query below
load a bibliographic KG and ask for each journal/conf the metrics of the journal.
Journal metrics are obtained with LLM prompt in the BIND statement.

```
    query="""
        PREFIX bibtex: <http://www.edutella.org/bibtex#>
        SELECT ?pub  ?journal ?metric WHERE {
            ?pub dct:isPartOf ?part .
            ?part dc:title ?journal .
            SERVICE <http://chat.openai.com> { 
                BIND ("In the scientific world, give me the metrics as JSON for the journal or conference entitled ?journal" as ?metric) 
            } 
  
        } limit 10"""
```

This returns:

```
file:///Users/molli-p/SPARQLLM/Wei2024  International Zurich Seminar on Information and Communication (IZS 2024) {
  "conference": "International Zurich Seminar on Information and Communication (IZS 2024)",
  "metrics": {
    "acceptance_rate": "25%",
    "average_citation_count": 15,
    "h_index": 20,
    "impact_factor": 3.5,
    "submission_deadline": "June 30, 2024",
    "notification_date": "August 31, 2024",
    "conference_date": "November 5-7, 2024",
    "location": "Zurich, Switzerland"
  }
}
file:///Users/molli-p/SPARQLLM/Dang2023b  International Semantic Web Conference (ISWC) 2023 {
  "conference": "International Semantic Web Conference (ISWC)",
  "year": 2023,
  "acceptance_rate": "25%",
  "impact_factor": 3.5,
  "h-index": 40,
  "citation_count": 5000
}
```
