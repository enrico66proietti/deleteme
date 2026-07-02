from google import genai
import json
import base64
import os
import asyncio
from pydantic import BaseModel, Field



class ProfSkill(BaseModel):
    is_cv: bool = Field(description="True if the document is a CV, False otherwise.")
    name: str = Field(description="The name of CV candidate.")
    prename: str = Field(description="The prename if CV candidate.")
    university: str = Field(description="University where CV candidate got degree.")
    city: str = Field(description="The city where the candidate resides.")
    keyword_scores: dict[str, int] = Field(description="Scores from 0 to 4 for each provided keyword.")
    summary:    str = Field(description=" Summary of whole document.")

class JobMatch(BaseModel):
    job_position: str = Field(description="The title of the job position.")
    matching_score: int = Field(description="A score from 0 to 100 representing the skill match.")
    url: str = Field(description="URL of the job posting.")

class BackgroundVerification(BaseModel):
    matches: list[JobMatch] = Field(description="A list of the top matching job positions.")
    #matching_scores: dict[str, int] = Field(description="A score from 0 to 100 representing how accurately the skills in PDF matches the online job position .")
    #linkRef: str = Field(default=None, description="URL of the most matching online profile. Set to null if none is found.")

def verify_candidate_background(previous_interaction_id: str) -> BackgroundVerification:
    """
    Step 2: Uses a Two-Phase pipeline.
    Phase A: Search the web and return raw text.
    Phase B: Parse that raw text into strictly validated JSON.
    """
    client = genai.Client()
    
    # ---------------------------------------------------------
    # PHASE A: The Search Phase (NO JSON FORMATTING)
    # ---------------------------------------------------------
    print("-> Phase A: Conducting Google Search for job matches...")
    
    search_interaction = client.interactions.create(
        model="gemini-2.5-flash",
        previous_interaction_id=previous_interaction_id,
        system_instruction="""
        You are a job finder for IT technical area in internet sites.
        
        Task:
        1. Review the candidate info extracted in the previous turn (name, prename, university, city).
        2. Perform a background search using Google Search to search the internet for job positions most matching with main skills for this candidate.
        3. If there are too many results, restrict the results to 15 items and order them for date.
        4. Calculate a 'matching' score (0 to 100) for each job position.
        5. Provide the URLs of matching profiles. 
           CRITICAL RULE: DO NOT use "vertexaisearch.cloud.google.com" redirect URLs. You must extract and provide the actual, direct target URL (e.g., https://www.linkedin.com/jobs/..., https://www.indeed.com/...).
        """,
        tools=[{"type": "google_search"}],
        input="Perform the search for the most matching job positions using the candidate skills discovered in the previous turn."
    )
    
    # Print the raw markdown for debugging so you can see what it found
    print("\n--- PHASE A RAW OUTPUT ---")
    print(search_interaction.output_text)
    print("--------------------------\n")

    # Safety check: Did it get blocked?
    if not search_interaction.output_text:
        print("[!] ERROR: The model returned an empty response. Returning fallback.")
        return BackgroundVerification(matches=[{"job_position": "Blocked", "matching_score": 0, "url": "BLOCKED"}])

   # ---------------------------------------------------------
    # PHASE B: The Parsing Phase (STRICT JSON, NO TOOLS)
    # ---------------------------------------------------------
    print("-> Phase B: Forcing the search results into strict JSON format...")
    
    format_interaction = client.interactions.create(
        model="gemini-2.5-flash",
        system_instruction="You are a strict data formatting agent. Convert the provided text into the exact JSON schema requested. DO NOT wrap the output in markdown code blocks.",
        input=f"""
        Analyze the text below and extract the job matches into a single JSON object matching the schema.
        
        CRITICAL RULES for JSON keys:
        - The root must be a JSON object containing a "matches" key.
        - Inside "matches", each item MUST use these exact field names:
          1. "job_position" (string - do not use 'job_position_title')
          2. "matching_score" (integer)
          3. "url" (string)
        
        TEXT TO PARSE:
        {search_interaction.output_text}
        """,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": BackgroundVerification.model_json_schema()
        }
    )

    # --- THE BULLETPROOF CLEANER ---
    clean_json_string = format_interaction.output_text.strip()
    if clean_json_string.startswith("```json"):
        clean_json_string = clean_json_string[7:]
    if clean_json_string.endswith("```"):
        clean_json_string = clean_json_string[:-3]
    clean_json_string = clean_json_string.strip()

    # --- THE LIST INTERCEPTOR ---
    # If Gemini ignores instructions and sends a raw list [ ... ], 
    # we manually wrap it into the object {"matches": [ ... ]} Pydantic wants.
    if clean_json_string.startswith("["):
        print("[!] Note: Model returned a raw list. Auto-wrapping into object format...")
        clean_json_string = f'{{"matches": {clean_json_string}}}'

    # Now we pass it to Pydantic completely safe
    result = BackgroundVerification.model_validate_json(clean_json_string)
    return result

   

#async def analyze_cv(pdf_path: str, keywords: list):
def analyze_cv(pdf_path: str, keywords: list):
    if not os.path.exists(pdf_path):
            return {"error": f"File {pdf_path} not found"}

    client = genai.Client()

    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()


    interaction = client.interactions.create(
        model="gemini-3.5-flash",
        system_instruction = """
        You are a Professional CV Screening and Background Check Agent.

        Task Rules:
        1. Verify if the uploaded document is a CV/Resume. If it is NOT, return exactly: {"error": "Not a CV"}.
        2. If it is a CV, extract the candidate's full name  , the city where he live and the univerity he studied if declared.
        3. Score the candidate from 0 to 7 against the main 10 skill keywords present in the PDF

        """,

        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": ProfSkill.model_json_schema()

        },

        input=[
            {
                "type": "document",
                "data": base64.b64encode(pdf_bytes).decode('utf-8'),
                "mime_type": "application/pdf"
            },
            {"type": "text", "text": f"Is this a curriculum vitae?Summarize this document and score it against the 10 more frequent skill keywords."}
        ]
    )

   

    result = ProfSkill.model_validate_json(interaction.output_text)
    return(result, interaction.id)



# --- Execution ---

#async def main():
def main():
    target_keywords = ["Python", "SQL", "Machine Learning", "Cloud Computing"]
    pdf_file = "./document.pdf" # Make sure this file exists


    print(f"--- Analyzing and verifying: {pdf_file} ---")

    #result = await analyze_cv(pdf_file, target_keywords)
    result, interaction_id = analyze_cv(pdf_file, target_keywords)

    # Final output
    print(f"Interaction ID: {interaction_id}")
    print(result.model_dump_json(indent=2))


    print("-" * 50)

    # Step 2: Run verification using the returned interaction ID
    verification = verify_candidate_background(interaction_id)
    print("\nStep 2 Complete!")
    print(verification.model_dump_json(indent=2))


if __name__ == "__main__":
#    asyncio.run(main())
    main() 
