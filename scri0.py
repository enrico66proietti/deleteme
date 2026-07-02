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

class BackgroundVerification(BaseModel):
    truthfulness: int = Field(description="A score from 0 to 100 representing how accurately the PDF matches the online profile.")
    linkRef: str = Field(default=None, description="URL of the most matching online profile. Set to null if none is found.")
    debuRef1: str = Field(default=None, description="URL of an online profile found during background check.")
    debuRef2: str = Field(default=None, description="URL of another online profile found during background check.")

def verify_candidate_background(previous_interaction_id: str) -> BackgroundVerification:
    """
    Step 2: Use the previous interaction context, execute a web search background check,
    and output verification results.
    """
    client = genai.Client()
    
    print("-> Running Step 2: Conducting Google Search background check...")
    
    # previous_interaction_id carries the context of Step 1 on the server.
    # System instructions, tools, and schemas are interaction-scoped, so they are re-specified.
    interaction = client.interactions.create(
        model="gemini-2.5-flash",
        previous_interaction_id=previous_interaction_id,
        system_instruction="""
        You are a Background Check Verification Agent.
        
        Task:
        1. Review the candidate info extracted in the previous turn (name, prename, university, city).
        2. Perform a background check using Google Search to search the internet (specifically linkedin.com site) for this candidate.
        3. If there are too many results, restrict the search using earlier companies they worked at.
        4. Compare the experience/skills claimed in the PDF with the information found online.
        5. Calculate a 'truthfulness' score (0 to 100).
        6. Provide the URLs of matching profiles.
        """,
        tools=[{"type": "google_search"}],
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": BackgroundVerification.model_json_schema()
        },
        input="Perform the background check on the candidate discovered in the previous turn."
    )
   # 1. Check if the model actually returned text
    if not interaction.output_text:
        print("\n[!] ERROR: The model returned an empty response (output_text is None).")
        print("This usually means it was blocked by safety filters or returned a raw tool call.")
        print("--- RAW API RESPONSE FOR DEBUGGING ---")
        print(interaction)
        print("--------------------------------------")
        # Return a fallback or empty object so the script doesn't crash
        return BackgroundVerification(truthfulness=0, linkRef="BLOCKED", debuRef1=None, debuRef2=None)

    # 2. If text exists, validate it normally
        print("--- RAW API RESPONSE FOR DEBUGGING ---")
        print(interaction)
        print("--------------------------------------")
    result = BackgroundVerification.model_validate_json(interaction.output_text)
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
        3. Score the candidate from 0 to 4 against the provided keywords based on the PDF content:

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
            {"type": "text", "text": f"Is this a curriculum vitae?Summarize this document and score it against these keywords: {', '.join(keywords)}."}
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
