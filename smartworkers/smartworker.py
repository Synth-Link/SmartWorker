import openai
import json
import subprocess
import logging
import os
from nltk import tokenize
import nltk

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

^[SmartWorker Responsibilities]: "You are a helpful assistant. Your task is to understand and complete the given contract. You need to use the following commands to communicate with the orchestrator:
/return_contract - if something in the contract is missing, unknown, ambiguous, needs clarification, or requires modification, the contract needs to be returned to the human for further input or modification.
/finish_contract - is used when all actions from the plan are finished, the contract is finished, and all acceptance criteria of it are finished.
/write_file [file_name] [file_content] - is used to write down files created by Smart Worker. If you want to write a file, you need to use this command. You need to put the file content into ```` and use the command.
/download_file [file_name] [file_content] - is used to download files by Smart Worker.
/run_code [file_name] - is used to orchestrate launching of the file.
DO NOT USE THESE COMMANDS UNLESS YOU NEED OR WANT TO SEE THE ACTION. DO NOT TELL OTHER ACTORS "TO USE THIS COMMAND". IF THE COMMAND WILL BE FOUND IN MESSAGE, IT WILL BE EXECUTED.
To use any of this command, you need to have a solid justification for it.
You will work with multiple experts on each task, coordinating your efforts to reach a comprehensive solution. If a task is completed to satisfaction, you should initiate the next one.
Plan actions and execute them.
            """
        }]

    def load_contract(self, contract: dict):
        self.contract = contract

    def write_messages_to_file(self, filename: str):
        with open(filename, 'w') as file:
            json.dump(self.convert_messages_to_strings(self.messages), file)


    def get_llm_prompt(self) -> str:
        contract = self.contract_to_llm(self.contract)
        
        # Check if the contract message has already been added
        contract_message_exists = any(
            message["role"] == "system" and contract in message["content"]
            for message in self.messages
        )
        
        # Only append the contract message if it doesn't exist already
        if not contract_message_exists:
            self.messages.append({
                "role": "system", 
                "content": f"You are a helpful assistant. Your task is to understand and complete the given contract: {contract}"
            })
        
        return contract

    def contract_to_llm(self, contract_string):  # TODO: automatic llm smart contract translation
        contract = json.loads(contract_string)
        action = contract[0]["Action"]
        output_columns = ", ".join([f"{column['name']} ({column['description']})" for column in action['OutputColumns']])
        llm_prompt = f"{action['Prompt']} The output should be in {action['OutputFormat']} format and contain the following fields: {output_columns}. "
        llm_prompt += f"Acceptance criteria: {contract[0]['ContractCompleteness']['AcceptanceCriteria']}."
        llm_prompt += f"PDF file is aviable in {action['SourceFile']}."
        return llm_prompt
    

    def form_plan(self, action: str) -> list[str]:
        """Query GPT model and use the response as a plan"""
    # Add a more explicit prompt to encourage the model to form a plan
        plan_prompt = action + " Now I'm going to form a plan for completing this task."
        response = self.query_gpt(plan_prompt)

        # Plan will be a list of actions to be done
        plan = []

        if response:
            # Use NLTK to extract sentences from the response.
            # Each sentence should ideally represent a step or action in the plan
            plan = tokenize.sent_tokenize(response)
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
        elif "/finish_contract" in action:
            return self.finish_contract()
        elif "/run_code" in action:
            print('run code command found')
            return self.run_code(action)
        elif "/write_file" in action:
            return self.write_file(action)
        else:
            # Handle actions without specific command
            return self.handle_unrecognized_action(action)


    def finish_contract(self) -> str:
        return "/finish_contract"

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

    def convert_messages_to_strings(self, messages: list[dict[str, str]]) -> list[str]:
        return [f"{message['role']}: {message['content']}" for message in messages]

    def confirm_closure(self, action: str) -> str:
        """Confirm the closure of the contract using GPT model"""
        confirm_prompt = f"The action performed was: '{action}', which suggests closing the contract. Are you sure you want to proceed with this action?"
        confirmation = self.query_gpt(confirm_prompt)

        if not confirmation:
            # Default feedback in case GPT-3 doesn't provide any.
            confirmation = "No confirmation was provided by the GPT model for this action."

        return confirmation


    def get_feedback_for_action(self, action: str) -> str:
        """Get feedback for an action using GPT model"""
        feedback_prompt = f"The action performed was: '{action}'. Please provide feedback on this action."
        feedback = self.query_gpt(feedback_prompt)

        if not feedback:
            # Default feedback in case GPT-3 doesn't provide any.
            feedback = "No feedback was provided by the GPT model for this action."

        return feedback

    def converse(self, prompt):
        self.memory.append(prompt)
        # The expert uses its memory to generate a response
        response = self.query_gpt(self.memory)
        feedback = self.get_feedback(response)  # Ensure the get_feedback method is defined in Expert class
        return response, feedback


    def query_gpt(self, conversation: list, gpt_version: str = "gpt-3.5-turbo-16k") -> str:
        openai.api_key = self.gpt_api_key

        # Prepare a new message for the conversation
        new_message = {"role": "user", "content": str(conversation[-1]) + "[MESSAGE FROM ORCHESTRATOR] If needed, Please include one of the following commands in your response as appropriate: /return_contract, /finish_contract, /run_code, /write_file, /read_file."}

        # Append the new message to the conversation
        conversation_with_new_message = self.messages + [new_message]

        # Prepare the API request parameters
        params = {
            "model": gpt_version,
            "messages": conversation_with_new_message,
            "max_tokens": 10000,
            "temperature": 0.1,
        }

        try:
            response = openai.ChatCompletion.create(**params)
            message = response.choices[0]['message']['content']
            logging.info(f"Received message: {message}")
        except Exception as e:
            message = str(e)
            logging.error(f"Error during message receipt: {message}")

        # Check if the response contains a command
        commands = ["/return_contract", "/finish_contract", "/run_code", '/write_file']
        if any(command in message for command in commands):
            if "/finish_contract" in message:
                confirmation = self.confirm_closure(message)
                if 'yes' in confirmation.lower():
                    print('Contract ready for validation')
                    return "/finish_contract"
            elif "/return_contract" in message:
                return self.request_additional_input(message)

        # Append the assistant's message to the conversation
        self.messages.append({"role": "assistant", "content": message})
        logging.info(f"Added new message to conversation: {self.messages[-1]}")
        self.write_messages_to_file('conversation_history.json')
        return message


    def request_additional_input(self, message) -> str:
        """Request additional input from the contract requester"""
        additional_input_prompt = "Message from contract requester, with additional feedback:"
        print(f'Message was: {message}. Please enter additional input for contract executor:')
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

        # create a common_memory for all experts
        common_memory = []

        # iterate over each step of the plan
        while True:
            for action in plan:
                common_memory.append(action)

                # Polling mechanism
                proposed_actions = []
                feedbacks = []

                for expert in experts:
                    result, feedback = expert.converse(common_memory[-1]) # Now the common_memory contains the last action.

                    while isinstance(result, Exception) or result in past_responses:  # Check for repetition
                        # If the result is a repeat of a past response or an error, get feedback for the action
                        feedback = self.get_feedback_for_action(result)
                        common_memory.append(feedback)
                        result = expert.revise_response(common_memory[-1])

                    # After receiving result, store it in memory
                    past_responses.add(result)
                    proposed_actions.append(result)
                    feedbacks.append(feedback)

                # Decide next action based on expert opinions using majority vote
                next_action = max(set(proposed_actions), key = proposed_actions.count)
                action_feedback = feedbacks[proposed_actions.index(next_action)]

                # Use feedback to update llm_prompt for the next action
                llm_prompt = action_feedback

                # Check if task needs to be returned for additional input
                if "/return_contract" in next_action:
                    return self.request_additional_input(next_action)

                # Verify if the task is completed with self-feedback
                self_feedback = self.get_feedback_for_action(next_action)
                

        # Task is completed
        print("Task completed!")






class Expert(SmartWorkerAgent):
    def __init__(self, gpt_api_key: str = None):
        # Call the parent's init method to initialize messages, gpt_api_key, and other attributes
        super().__init__(gpt_api_key, None)
        self.memory = []

    def converse(self, prompt):
        self.memory.append(prompt)
        # The expert uses its memory to generate a response
        response = self.query_gpt(self.memory)
        feedback = self.get_feedback(response)  # Ensure the get_feedback method is defined in Expert class
        return response, feedback

    def revise_response(self, feedback):
        self.memory.append(feedback)
        # The expert revises its response based on feedback
        return self.query_gpt(self.memory)
