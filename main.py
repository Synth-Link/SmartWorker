#from smartworkers.smartworker import SmartWorker
from smartworkers.smartworker import SmartWorkerAgent
import os
import json
from dotenv import load_dotenv


def main():
    load_dotenv()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    contract_string = """
    [{
    "Action": {
        "Prompt": "Data extraction from AMDT (amendment document) of Aeronautical Information Publications (AIP).",
        "OutputColumns": [
        { "name": "type", "description": "Data type indication: O for Obstacle A for Airspace" },
        { "name": "icao_identifier", "description": "ICAO code of affected airspace or airport" },
        { "name": "details", "description": "Details of airspace or obstacle" },
        { "name": "vertical_amsl", "description": "Vertical information about the object in AMSL in feet (ft)" },
        { "name": "vertical_agl", "description": "Vertical AGL information if provided" },
        { "name": "horizontal", "description": "Horizontal points provided as JSON" }
        ],
        "OutputFormat": "json"
    },
    "Validation": "The data must be double extracted for verification from the source document. The data must be aligned with ADQ (Aeronautical Data Quality) Standard.",
    "WorkerRequirements": { "Skills": ["PDF splitting dividing", "Data extraction", "Data engineering"] },
    "ValidatorRequirements": { "Certifications": ["EASA certified AI model for aeronautical data"] },
    "ContractCompleteness": {
        "AcceptanceCriteria": "The contract is completed when the data is extracted and validated with prompts.",
        "ErrorAcceptance": "0%",
        "AmbiguityAcceptance": "5%"
    },
    "ContractFail": "Validation or Action is not completed by the network.",
    "ContractValue": { "Budget": "10 DOT" }
    }]
    """

    print(contract_string)
    worker = SmartWorkerAgent(OPENAI_API_KEY, "gpt-3.5-turbo-16k")

    # Here we load the contract into the worker
    worker.load_contract(contract_string)
    results = worker.handle_action(contract_string)

    # Here we just print the results, but in reality you might want to save them somewhere or use in another way
    print("OUTPUTS:",results)


if __name__ == "__main__":
    main()
