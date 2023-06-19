import openai
import json
import subprocess

class SmartWorkerAgent:
    def __init__(self, gpt_api_key: str, gpt_model: str):
        self.memory = []
        self.gpt_model = gpt_model
        self.gpt_api_key = gpt_api_key
        self.contract = None
        self.messages = [{"role": "system", "content": f"You are a helpful assistant. Your task is to understand and complete the given contract: {self.contract}"}]

    def load_contract(self, contract: dict):
        self.contract = contract

    def get_llm_prompt(self) -> str:
        contract = self.contract_to_llm(self.contract)
        self.messages = [{"role": "system", "content": f"You are a helpful assistant. Your task is to understand and complete the given contract: {contract}"}]
        contract = self.contract_to_llm(self.contract)
        return contract

    def contract_to_llm(self, contract_string):
        contract = json.loads(contract_string)
        action = contract[0]["Action"]
        output_columns = ", ".join([f"{column['name']} ({column['description']})" for column in action['OutputColumns']])
        llm_prompt = f"{action['Prompt']} The output should be in {action['OutputFormat']} format and contain the following fields: {output_columns}. "
        llm_prompt += f"Acceptance criteria: {contract[0]['ContractCompleteness']['AcceptanceCriteria']}."
        return llm_prompt

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

        # Iterate through the plan and process each step
        for step in plan:
            result = self.process_step(step)

            # If an error occurs while processing a step, 
            # get feedback and revise the plan
            if isinstance(result, Exception):
                self_feedback = self.get_feedback(result)
                plan = self.revise_plan(plan, result)

        return self_feedback


    def handle_action(self, action: str) -> str:
        if "/return_contract" in action:
            return self.return_contract()
        elif "/ready_for_validation" in action:
            return self.ready_for_validation()
        elif "/run_code" in action:
            return self.run_code(action)
        elif "/write_file" in action:
            return self.write_file(action)
        else:
            # Handle actions without specific command
            return self.handle_unrecognized_action(action)

    def return_contract(self) -> str:
        return "/return_contract"

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
        conversation = self.memory + [prompt]
        response = self.query_gpt(conversation)
        if any(flag in response for flag in ["/return_contract", "/ready_for_validation", "/run_code", "/write_file"]):
            return self.handle_action(response)
        return response

    def query_gpt(self, prompt: str, gpt_version: str = "gpt-3.5-turbo-16k", tokens: int = 60) -> str:
        openai.api_key = self.gpt_api_key
        
        # Appending user's message
        self.messages.append({"role": "user", "content": prompt})

        try:
            response = openai.ChatCompletion.create(
                model=gpt_version,
                messages=self.messages,
                max_tokens=tokens,
                n=1,
                stop=None,
                temperature=0.6,
                log_level="info",
            )
            message = response['choices'][0]['message']['content']
        except Exception as e:
            message = str(e)

        # Appending assistant's message
        self.messages.append({"role": "assistant", "content": message})

        return message

    def execute(self):
        llm_prompt = self.get_llm_prompt()
        while True:
            action = self.converse(llm_prompt)
            feedback = self.get_feedback(action)
            if "/ready_for_validation" in feedback:
                break
            elif "/return_contract" in feedback:
                # Insert your code to handle returning contract
                pass
            llm_prompt = feedback