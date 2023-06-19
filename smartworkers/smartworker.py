import openai
import json
import subprocess

class SmartWorkerAgent:
    def __init__(self, gpt_api_key: str, gpt_model: str):
        self.memory = []
        self.gpt_model = gpt_model
        self.gpt_api_key = gpt_api_key
        self.contract = None
        self.messages = [{"role": "system", "content": 
        """You are a helpful assistant. Your task is to understand and complete the given contract. You can use the following flags to communicate with the orchestrator:
        /return_contract - if something in the contract is missing, unknown, ambiguous, needs clarification, the contract needs to be returned to the human for further input or modification.
        /ready_for_validation - is used when all actions from the plan are finished, the contract is finished, and all acceptance criteria of it are finished.
        /write_file [file_name] [file_content] - is used to write down files.
        /run_code [file_name] - is used to orchestrate launching of the file.
        """
        }]

    def load_contract(self, contract: dict):
        self.contract = contract

    def get_llm_prompt(self) -> str:
        contract = self.contract_to_llm(self.contract)
        # Here we append a new system message instead of overwriting the entire messages list
        self.messages.append({"role": "system", "content": f"You are a helpful assistant. Remember to use flags (/return_contract, /ready_for_validation, /write_file, /run_code) Your task is to understand and complete the given contract: {contract}"})
        return contract

    def contract_to_llm(self, contract_string):
        contract = json.loads(contract_string)
        action = contract[0]["Action"]
        output_columns = ", ".join([f"{column['name']} ({column['description']})" for column in action['OutputColumns']])
        llm_prompt = f"{action['Prompt']} The output should be in {action['OutputFormat']} format and contain the following fields: {output_columns}. "
        llm_prompt += f"Acceptance criteria: {contract[0]['ContractCompleteness']['AcceptanceCriteria']}."
        return llm_prompt
    
    #TODO: Add plan prompting to the function "Now I'm going to do the following step from the plan " " "
    def form_plan(self, action: str) -> list[str]:
        """Query GPT model and use the response as a plan"""
        # Plan will be a list of actions to be done
        plan = []
        response = self.query_gpt(action)
        if response:
            # Here we simply use each line in the response as a separate action
            plan = response.split('\n')
        return plan
        
    def handle_unrecognized_action(self, action: str) -> str:
    # Fetch self-feedback for the action
        self_feedback = self.get_feedback(action)

        # Plan next steps
        plan = self.form_plan(action)

        # Iterate through the plan
        i = 0
        while i < len(plan):
            step = plan[i]
            result = self.query_gpt(step)

            # If an error occurs while processing a step, 
            # get feedback and revise the plan
            if isinstance(result, Exception):
                self_feedback = self.get_feedback(result)
                plan = self.revise_plan(plan, result)
            else:
                # If the step was completed successfully, move to the next step
                i += 1

        return self_feedback


    def handle_action(self, action: str) -> str:
        if "/return_contract" in action:
            return self.request_additional_input()
        elif "/ready_for_validation" in action:
            return self.ready_for_validation()
        elif "/run_code" in action:
            return self.run_code(action)
        elif "/write_file" in action:
            return self.write_file(action)
        else:
            # Handle actions without specific command
            return self.handle_unrecognized_action(action)


    def ready_for_validation(self) -> str:
        return "/ready_for_validation"

    def run_code(self, action: str) -> str:
        filename = self.validate_filename(action)
        if filename is not None:
            os.system(f'python {filename}')
            return f"Executed {filename}"
        else:
            return "Invalid filename."

    def write_file(self, action: str) -> str:
        filename, file_content = self.validate_file_input(action)
        if filename is not None and file_content is not None:
            with open(filename, 'w') as file:
                file.write(file_content)
            return f"Written to {filename}"
        else:
            return "Invalid file input."

    def validate_filename(self, action: str) -> str:
        filename = action.split(" ")[1] if len(action.split(" ")) > 1 else None
        return filename

    def validate_file_input(self, action: str) -> (str, str):
        parts = action.split(" ")
        filename = parts[1] if len(parts) > 2 else None
        file_content = " ".join(parts[2:]) if len(parts) > 2 else None
        return filename, file_content
    
    def get_feedback(self, action: str) -> str:
        if "/run_code" in action:
            filename = self.validate_filename(action)
            if filename is not None:
                try:
                    # Running the file and capturing output
                    process = subprocess.run(['python', filename], capture_output=True, text=True)
                    feedback = process.stdout
                except Exception as e:
                    feedback = str(e)
            else:
                feedback = "Invalid filename."
        else:
            feedback = action
        return feedback


    def converse(self, prompt: str) -> str:
        if isinstance(prompt, dict):
            prompt = json.dumps(prompt)
        elif not isinstance(prompt, str):
            prompt = str(prompt)
        
        conversation = self.memory + [prompt]
        response = self.query_gpt(conversation)
        if any(flag in response for flag in ["/return_contract", "/ready_for_validation", "/run_code", "/write_file"]):
            return self.handle_action(response)
        return response

    def query_gpt(self, conversation: list, gpt_version: str = "gpt-3.5-turbo-16k") -> str:
        openai.api_key = self.gpt_api_key

        # Prepare a new message for the conversation
        new_message = {"role": "user", "content": conversation[-1]}

        # Append the new message to the conversation
        self.messages.append(new_message)

        # Prepare the API request parameters
        params = {
            "model": gpt_version,
            "messages": self.messages,
            "max_tokens": 10000,
            "temperature": 0.6,
        }

        try:
            response = openai.ChatCompletion.create(**params)
            message = response.choices[0]['message']['content']
        except Exception as e:
            message = str(e)

        # Append the assistant's message to the conversation
        self.messages.append({"role": "assistant", "content": message})
        print(message)
        return message

    def request_additional_input(self) -> str:
        """Request additional input from the contract requester"""
        additional_input_prompt = "Message from contract requester, with additional feedback:"
        input_str = input()
        additional_input_prompt += input_str
        # Add the additional input prompt as a user message in the conversation
        self.messages.append({"role": "user", "content": additional_input_prompt})
        return additional_input_prompt

    def execute(self):
        llm_prompt = self.get_llm_prompt()
        while True:
            #print(llm_prompt)
            action = self.converse(llm_prompt)
            feedback = self.get_feedback(action)
            llm_prompt = feedback