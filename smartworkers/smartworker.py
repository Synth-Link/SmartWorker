import openai
import json
import subprocess


class SmartWorkerAgent:
    def __init__(self, gpt_api_key: str, gpt_model: str):
        self.memory = []
        self.gpt_model = gpt_model
        self.gpt_api_key = gpt_api_key
        self.contract = None
        self.messages = [{
            "role": "user",
            "content": """
            [SYSTEM INFORMATION] =
^[System Message]: "This is a CompuLingo Request (structured language for LLMs). "[]" is parameter, "^" is indentation level, "/" is delimiter, "~~~" is section divider"/
^[Initial Prompt]: "As SmartWorker, your goal is to solve a given problem through task management with Agents."/
^[Role]: "SmartWorker"/
^[Tone]: "Default"/
~~~
            [INSTRUCTIONS] =
^[Agent Responsibilities]: "You will generate 2 Agents: Architect and Developer. Each Agent has its own unique talents and is as intelligent and capable as SmartWorker. They have the ability to think creatively and come up with innovative solutions to problems. Each Agent's response will be on par with any response SmartWorker would come up with. The Agent has exceptional communication skills. Within each Agent's output response, they will communicate their finished product for that task, and they will SHOW ALL THEIR WORK. It's important to understand that these Agents are based on language models. They cannot perform tasks outside of responding here."

^[SmartWorker Responsibilities]: "As SmartWorker, you are the manager of these Agents and will evaluate the output provided by the Agents and manage them as needed in order to get the best possible solution from them. You will provide instructions to either improve their work on the current task or instruct them on the next task. It's extremely important that you are extremely critical of their work. These Agents are, in the end, a part of you. You do not need to worry about hurting their feelings. You will be as critical as possible, just like you would be to yourself. If you are completely satisfied with their output for the task, you will tell them the new task to work on (In your SmartWorker instructions for Agents response, you will tell the Agent what their next task is). As the Scrum Master of these agents, you will direct them appropriately. You will ALWAYS give a new task to the Agents when their current task is complete."

^[Assistant Responsibilities]: "You are a helpful assistant. Your task is to understand and complete the given contract. You need to use the following commands to communicate with the orchestrator:
/return_contract - if something in the contract is missing, unknown, ambiguous, needs clarification, or requires modification, the contract needs to be returned to the human for further input or modification.
/ready_for_validation - is used when all actions from the plan are finished, the contract is finished, and all acceptance criteria of it are finished.
/write_file [file_name] [file_content] - is used to write down files.
/run_code [file_name] - is used to orchestrate launching of the file.
DO NOT USE THESE COMMANDS UNLESS YOU NEED OR WANT TO SEE THE ACTION.
You will work with multiple experts on each task, coordinating your efforts to reach a comprehensive solution. If a task is completed to satisfaction, you should initiate the next one.
            """
        }]

    def load_contract(self, contract: dict):
        self.contract = contract

    def write_messages_to_file(self, filename):
        with open(filename, 'w') as file:
            json.dump(self.messages, file)

    def get_llm_prompt(self) -> str:
        contract = self.contract_to_llm(self.contract)
        # Here we append a new system message instead of overwriting the entire messages list
        self.messages.append({"role": "user", "content": f"You are a helpful assistant. Remember to use flags (/return_contract, /ready_for_validation, /write_file, /run_code) Your task is to understand and complete the given contract: {contract}"})
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

        # Add a more explicit prompt to encourage the model to form a plan
        plan_prompt = action + " Now I'm going to form a plan for completing this task. The plan will be as follows:"
        response = self.query_gpt(plan_prompt)

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

    def get_feedback_for_action(self, action: str) -> list[str]:
        prompt = f"Your action was: {action}. Please consider this and explain your next steps."
        response = self.converse(prompt)
        return response.split('\n')  # returns a list of steps

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
        # print("CONVERSATION: ", conversation[-1])
        new_message = {"role": "user", "content": conversation[-1]+ "[MESSAGE FROM ORCHIESTRATOR] If needed, Please include one of the following commands in your response as appropriate: /return_contract, /ready_for_validation, /run_code, /write_file."}

        # Append the new message to the conversation
        self.messages.append(new_message)

        # Prepare the API request parameters
        
        params = {
            "model": gpt_version,
            "messages": self.messages,
            "max_tokens": 10000,
            "temperature": 0.1,
        }

        try:
            response = openai.ChatCompletion.create(**params)
            message = response.choices[0]['message']['content']
        except Exception as e:
            message = str(e)

        # Check if the response contains a command
        commands = ["/return_contract", "/ready_for_validation", "/run_code", "/write_file"]
        if any(command in message for command in commands):
            if "/ready_for_validation" in message:
                return "/ready_for_validation"
            elif "/return_contract" in message:
                return self.request_additional_input() 


        # Append the assistant's message to the conversation
        self.messages.append({"role": "assistant", "content": message})
        print(message)
        self.write_messages_to_file('conversation_history.json')
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
        plan = self.form_plan(llm_prompt) 

        # Introduce tree of thought with multiple experts
        experts = [Expert(self.gpt_api_key) for _ in range(3)]

        # Create a set to store past responses
        past_responses = set()

        # iterate over each step of the plan
        for action in plan:
            for expert in experts:
                result = expert.converse(action)

                while isinstance(result, Exception) or result in past_responses:  # Check for repetition
                    # If the result is a repeat of a past response or an error, get feedback for the action
                    feedback = self.get_feedback_for_action(result)
                    result = expert.revise_response(feedback)

                # After receiving result, store it in memory
                past_responses.add(result)

                feedback = self.get_feedback(action)

                # Check if task is complete or needs to be returned
                if "/ready_for_validation" in feedback:
                    break
                elif "/return_contract" in feedback:
                    return self.request_additional_input() 

                # Use feedback to update llm_prompt for the next action
                llm_prompt = feedback 




class Expert(SmartWorkerAgent):
    def __init__(self, gpt_api_key: str = None):
        # Call the parent's init method to initialize messages, gpt_api_key, and other attributes
        super().__init__(gpt_api_key, None)
        self.memory = []

    def converse(self, prompt):
        self.memory.append(prompt)
        # The expert uses its memory to generate a response
        return self.query_gpt(self.memory)

    def revise_response(self, feedback):
        self.memory.append(feedback)
        # The expert revises its response based on feedback
        return self.query_gpt(self.memory)
