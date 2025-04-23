import os
import json
import re
import requests
import base64
import time

# Since we can't import from _pipeline, let's include the necessary functions here
def load_config():
    """
    Load config file looking into multiple locations
    """
    config_locations = [
        "./_config",
        "prompt-eng/_config",
        "../_config"
    ]
    
    # Find CONFIG
    config_path = None
    for location in config_locations:
        if os.path.exists(location):
            config_path = location
            break
    
    if not config_path:
        raise FileNotFoundError("Configuration file not found in any of the expected locations.")
    
    # Load CONFIG
    with open(config_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()


def create_payload(model, prompt, target="ollama", **kwargs):
    """
    Create the Request Payload in the format required by the Model Server
    """
    payload = None
    if target == "ollama":
        payload = {
            "model": model,
            "prompt": prompt, 
            "stream": False,
        }
        if kwargs:
            payload["options"] = {key: value for key, value in kwargs.items()}

    elif target == "open-webui":
        payload = {
            "model": model,
            "messages": [ {"role" : "user", "content": prompt } ]
        }
    else:
        print(f'!!ERROR!! Unknown target: {target}')
    return payload


def model_req(payload=None):
    """
    Issue request to the Model Server
    """
        
    # CUT-SHORT Condition
    try:
        load_config()
    except Exception as e:
        print(f"Error loading config: {e}")
        return -1, f"!!ERROR!! Problem loading config: {e}"

    url = os.getenv('URL_GENERATE', None)
    api_key = os.getenv('API_KEY', None)
    delta = response = None

    headers = dict()
    headers["Content-Type"] = "application/json"
    if api_key: headers["Authorization"] = f"Bearer {api_key}"

    print(f"Making request to: {url}")
    print(f"Payload: {payload}")

    # Send out request to Model Provider
    try:
        start_time = time.time()
        response = requests.post(url, data=json.dumps(payload) if payload else None, headers=headers)
        delta = time.time() - start_time
    except Exception as e:
        return -1, f"!!ERROR!! Request failed: {e}. You need to adjust _config with URL({url})"

    # Checking the response and extracting the 'response' field
    if response is None:
        return -1, f"!!ERROR!! There was no response (?)"
    elif response.status_code == 200:
        result = ""
        delta = round(delta, 3)

        response_json = response.json()
        if 'response' in response_json: ## ollama
            result = response_json['response']
        elif 'choices' in response_json: ## open-webui
            result = response_json['choices'][0]['message']['content']
        else:
            result = response_json 
        
        return delta, result
    elif response.status_code == 401:
        return -1, f"!!ERROR!! Authentication issue. You need to adjust _config with API_KEY ({url})"
    else:
        return -1, f"!!ERROR!! HTTP Response={response.status_code}, {response.text}"
    return

# Create output directories if they don't exist
os.makedirs("outputs/diagrams", exist_ok=True)
os.makedirs("outputs/code", exist_ok=True)

# Load prompt templates
def load_template(template_name):
    template_path = f"templates/{template_name}.txt"
    if os.path.exists(template_path):
        with open(template_path, "r") as f:
            return f.read()
    else:
        print(f"Warning: Template file {template_path} not found.")
        return ""

def extract_mermaid_diagrams(text):
    """Extract Mermaid diagrams from text"""
    pattern = r"```mermaid\s*(.*?)\s*```"
    diagrams = re.findall(pattern, text, re.DOTALL)
    return diagrams

def save_mermaid_diagram(diagram, filename):
    """Save Mermaid diagram to file"""
    with open(f"outputs/diagrams/{filename}.mmd", "w") as f:
        f.write(diagram)
    print(f"Saved diagram to outputs/diagrams/{filename}.mmd")

def render_mermaid_diagrams():
    """Render all Mermaid diagrams to PNG files using an online service"""
    # Get all .mmd files in the diagrams directory
    mmd_files = [f for f in os.listdir("outputs/diagrams") if f.endswith(".mmd")]
    
    for mmd_file in mmd_files:
        with open(f"outputs/diagrams/{mmd_file}", "r") as f:
            mermaid_code = f.read()
        
        # Encode the Mermaid code for the URL
        encoded = base64.b64encode(mermaid_code.encode("utf-8")).decode("utf-8")
        
        # Create the URL for the Mermaid Live Editor
        img_url = f"https://mermaid.ink/img/{encoded}"
        
        try:
            # Download the rendered image
            response = requests.get(img_url)
            if response.status_code == 200:
                output_file = mmd_file.replace(".mmd", ".png")
                with open(f"outputs/diagrams/{output_file}", "wb") as f:
                    f.write(response.content)
                print(f"Rendered {mmd_file} to {output_file}")
            else:
                print(f"Failed to render {mmd_file}: HTTP {response.status_code}")
        except Exception as e:
            print(f"Error rendering {mmd_file}: {e}")

def run_sdlc_pipeline(user_story, model="llama3"):
    """Run the complete SDLC pipeline from user story to implementation"""
    results = {}
    
    # Stage 1: Requirements
    print("\n--- Stage 1: Generating Requirements ---")
    req_template = load_template("requirements")
    req_payload = create_payload(
        target="ollama",
        model=model,
        prompt=req_template.format(user_story=user_story),
        temperature=0.7
    )
    _, requirements = model_req(payload=req_payload)
    if requirements.startswith("!!ERROR!!"):
        print(f"Error generating requirements: {requirements}")
        return {}
        
    results["requirements"] = requirements
    
    # Save requirements to file
    with open("outputs/requirements.txt", "w") as f:
        f.write(requirements)
    print("Requirements generated successfully and saved to outputs/requirements.txt")
    
    # Stage 2: Architecture
    print("\n--- Stage 2: Generating Architecture ---")
    arch_template = load_template("architecture")
    arch_payload = create_payload(
        target="ollama",
        model=model,
        prompt=arch_template.format(requirements=requirements),
        temperature=0.7
    )
    _, architecture = model_req(payload=arch_payload)
    if architecture.startswith("!!ERROR!!"):
        print(f"Error generating architecture: {architecture}")
        return results
        
    results["architecture"] = architecture
    
    # Save architecture to file
    with open("outputs/architecture.txt", "w") as f:
        f.write(architecture)
    
    # Extract and save architecture diagram
    arch_diagrams = extract_mermaid_diagrams(architecture)
    if arch_diagrams:
        save_mermaid_diagram(arch_diagrams[0], "architecture")
    print("Architecture generated successfully and saved to outputs/architecture.txt")
    
    # Stage 3: UML Diagrams
    print("\n--- Stage 3: Generating UML Diagrams ---")
    uml_template = load_template("uml")
    uml_payload = create_payload(
        target="ollama",
        model=model,
        prompt=uml_template.format(architecture=architecture),
        temperature=0.7
    )
    _, uml_diagrams = model_req(payload=uml_payload)
    if uml_diagrams.startswith("!!ERROR!!"):
        print(f"Error generating UML diagrams: {uml_diagrams}")
        return results
        
    results["uml_diagrams"] = uml_diagrams
    
    # Save UML diagrams to file
    with open("outputs/uml_diagrams.txt", "w") as f:
        f.write(uml_diagrams)
    
    # Extract and save UML diagrams
    diagrams = extract_mermaid_diagrams(uml_diagrams)
    for i, diagram in enumerate(diagrams):
        save_mermaid_diagram(diagram, f"uml_diagram_{i+1}")
    print("UML diagrams generated successfully and saved to outputs/uml_diagrams.txt")
    
    # Stage 4: Implementation
    print("\n--- Stage 4: Generating Implementation Code ---")
    impl_template = load_template("implementation")
    impl_payload = create_payload(
        target="ollama",
        model=model,
        prompt=impl_template.format(design=uml_diagrams),
        temperature=0.7
    )
    _, implementation = model_req(payload=impl_payload)
    if implementation.startswith("!!ERROR!!"):
        print(f"Error generating implementation: {implementation}")
        return results
        
    results["implementation"] = implementation
    
    # Save implementation code
    with open("outputs/code/implementation.py", "w") as f:
        f.write(implementation)
    print("Implementation code generated successfully and saved to outputs/code/implementation.py")
    
    # Render diagrams to images
    print("\n--- Rendering Diagrams to Images ---")
    render_mermaid_diagrams()
    
    return results

# Example usage
if __name__ == "__main__":
    user_story = """
    As a university student, I want a task management application that helps me organize my assignments, 
    track deadlines, set priorities, and receive reminders. The application should allow me to categorize 
    tasks by course, set recurring tasks for regular study sessions, and provide analytics on my productivity 
    and completion rates.
    """
    
    print("Starting SDLC Automation Pipeline...")
    print("User Story:", user_story)
    
    # Check for _config file
    config_locations = [
        "./_config",
        "prompt-eng/_config",
        "../_config"
    ]
    
    config_found = False
    for location in config_locations:
        if os.path.exists(location):
            config_found = True
            print(f"Found config at: {location}")
            break
    
    if not config_found:
        print("WARNING: No _config file found. Creating a sample configuration...")
        with open("./_config", "w") as f:
            f.write("URL_GENERATE=http://localhost:11434/api/generate\n")
            f.write("API_KEY=\n")
        print("Sample _config file created at ./_config")
        print("Please verify the URL is correct for your Ollama installation before proceeding.")
    
    # Run the pipeline
    results = run_sdlc_pipeline(user_story)
    
    # Print a summary of results
    if results:
        print("\nSDLC Pipeline Complete!")
        print("Generated files:")
        print("- Requirements: outputs/requirements.txt")
        print("- Architecture: outputs/architecture.txt and outputs/diagrams/architecture.png")
        print("- UML Diagrams: outputs/uml_diagrams.txt and outputs/diagrams/uml_diagram_*.png")
        print("- Implementation: outputs/code/implementation.py")
    else:
        print("\nSDLC Pipeline encountered errors. Please check the logs above.")