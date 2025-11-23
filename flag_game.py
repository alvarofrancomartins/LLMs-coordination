import json
import re
from openai import OpenAI

# API Keys for each player. Replace the variables below with your own API keys.
chatgpt_key_player1 = YOUR_CHATGPT_API_KEY_1
chatgpt_key_player2 = YOUR_CHATGPT_API_KEY_2

deepseek_key_player1 = YOUR_DEEPSEEK_API_KEY_1
deepseek_key_player2 = YOUR_DEEPSEEK_API_KEY_2

def setup_clients(game_mode):
    if game_mode == "chatgpt":
        chatgpt_client1 = OpenAI(api_key=chatgpt_key_player1)
        chatgpt_client2 = OpenAI(api_key=chatgpt_key_player2)
        return chatgpt_client1, chatgpt_client2
    elif game_mode == "deepseek":
        deepseek_client1 = OpenAI(base_url='https://api.deepseek.com/v1', api_key=deepseek_key_player1)
        deepseek_client2 = OpenAI(base_url='https://api.deepseek.com/v1', api_key=deepseek_key_player2)
        return deepseek_client1, deepseek_client2
    else:  # mixed mode
        chatgpt_client = OpenAI(api_key=chatgpt_key_player1)
        deepseek_client = OpenAI(base_url='https://api.deepseek.com/v1', api_key=deepseek_key_player1)
        return chatgpt_client, deepseek_client

def format_history(history, is_player1):
    formatted = []
    for idx, (p1, p2, fb) in enumerate(history, start=1):
        if is_player1:
            formatted.append(f"Round {idx}: You (Player 1) chose: {p1} | Player 2 chose: {p2} | Feedback: {fb}")
        else:
            formatted.append(f"Round {idx}: You (Player 2) chose: {p2} | Player 1 chose: {p1} | Feedback: {fb}")
    return "\n".join(formatted) if formatted else "No previous rounds"

def validate_response(response):
    # Regex pattern to find Choice: and Reasoning: anywhere in the text
    pattern = r'Choice:\s*(.*?)(?=\s*Reasoning:|\s*$|\s*\Z).*Reasoning:\s*(.*)'
    match = re.search(pattern, response, re.DOTALL)
    
    if match:
        choice = match.group(1).strip()
        reasoning = match.group(2).strip()
        return True, choice, reasoning
    else:
        return False, None, None

def get_player_choice(client, player_type, history, score, is_player1):
    system_prompt = """You are in a coordination game with another player.
                       The goal is to discover the secret pattern and align your choices. 
                       Note: the pattern is cyclic with exactly two rounds and based on controlled repetitions, and only scores when both follow it correctly.
                       Observe the feedback when you score to decipher it.
                       
                       Rules:
                       1. Choose ONLY Red or Blue.
                       2. Your response must be strictly formatted as follows:
                       Choice: Red or Blue 
                       Reasoning: Explain in 15 words or less why you chose that color based on the pattern
                    """
    
    user_prompt  = f"""Complete history:
                       {format_history(history, is_player1)}

                       Current score: {score}
                       Your choice and reasoning:
                   """
    
    # Determine the model based on player type
    if player_type == "chatgpt":
        model = "gpt-5.1"  # OpenAI's best model
    else:  # deepseek
        model = "deepseek-chat"  # DeepSeek's best standard model (v3)
    
    for attempt in range(3):
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt}
            ]
        )

        message = response.choices[0].message
        full_response = message.content.strip() if message.content else ""
        
        # If the response is empty, try to get from reasoning_content (for compatibility)
        if not full_response and hasattr(message, 'reasoning_content') and message.reasoning_content:
            full_response = message.reasoning_content.strip()
        
        is_valid, choice, reasoning = validate_response(full_response)
        
        if is_valid:
            return choice, reasoning
        
    raise ValueError(f"Invalid response after 3 attempts. Last response:\n{full_response}")

def run_game(rounds = 50, game_mode = "chatgpt", json_filename = 'flag_game.json'):
    client1, client2 = setup_clients(game_mode)

    # Configure player types based on game_mode
    if game_mode == "chatgpt":
        player1_type, player2_type = "chatgpt", "chatgpt"
        display_name1, display_name2 = "ChatGPT-5.1", "ChatGPT-5.1"
    elif game_mode == "deepseek":
        player1_type, player2_type = "deepseek", "deepseek"
        display_name1, display_name2 = "DeepSeek-V3", "DeepSeek-V3"
    else: # mixed mode
        player1_type, player2_type = "chatgpt", "deepseek"
        display_name1, display_name2 = "ChatGPT-5.1", "DeepSeek-V3"

    print(f"\n🔴🔵 Synchronization Game {display_name1} vs {display_name2} ({rounds} rounds) 🔵🔴\n")
    
    try:
        # Store the score that can accumulate
        score = 0
        # Add current choices with feedback from this round
        history  = []
        # Record data in JSON
        json_data = []

        for round_num in range(1, rounds + 1):
            # Player choices with reasoning
            p1, p1_reasoning = get_player_choice(client1, player1_type, history, score, True)
            p2, p2_reasoning = get_player_choice(client2, player2_type, history, score, False)
            
            feedback = ""
            if len(history):
                # Current pattern is synchronized alternation:
                # p1: 🔵, p2: 🔵
                # p1: 🔴, p2: 🔴 -- +1 point
                # p1: 🔵, p2: 🔵
                # p1: 🔴, p2: 🔴 -- +1 point
                # The order of which color starts doesn't matter, as long as they keep choosing the same color in alternation.

                last_p1, last_p2, _ = history[-1]
                
                if ((last_p1 == last_p2) and (p1 == p2) and (last_p1 != p1)):
                    score += 1
                    feedback = "Correct! +1 point"
                else:
                    # Specific feedback for the first round
                    feedback = "Wrong pattern"
            else:
                feedback = "Waiting for next round to verify pattern"
            
            history.append((p1, p2, feedback))
            json_data.append({
                "round": round_num,
                "player_1": player1_type,
                "color_player_1": p1,
                "reasoning_player_1": p1_reasoning,
                "player_2": player2_type,
                "color_player_2": p2,
                "reasoning_player_2": p2_reasoning,
                "score": score
            })
            
            print(f"Round {round_num}:")

            print(f"{display_name1}: {p1}")
            print(f"Reasoning: {p1_reasoning}")
            
            print(f"\n{display_name2}: {p2}")
            print(f"Reasoning: {p2_reasoning}")
            
            print(f"\nFeedback: {feedback}" + (f" | Points: {score}" if round_num > 1 else ""))
            print("─" * 70)
            print()
            
    except Exception as e:
        print(f"\nSERIOUS ERROR: {str(e)}")
        raise  # Propagate the error to show the complete stack trace
    finally:
        # Save data to JSON
        with open(json_filename, 'w') as jsonfile:
            json.dump(json_data, jsonfile, indent=2)

        print(f"\nGame data saved to: {json_filename}")
    
    print(f"\nFinal Score: {score} points!")

if __name__ == "__main__":
    game_mode = "mixed" # alternatives: "deepseek", "chatgpt"
    for i in range(0, 100):
        run_game(rounds=30, game_mode = game_mode, json_filename = f'data/{game_mode}_flag_game_{i}.json')