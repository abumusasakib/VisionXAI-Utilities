import pyperclip
import time
import re

def clean_whitespace(text: str) -> str:
    # Remove leading/trailing whitespace and reduce multiple spaces to one
    return re.sub(r'\s+', ' ', text.strip())

def main():
    last_text = None
    print("Monitoring clipboard. Press Ctrl+C to stop.")
    while True:
        try:
            current_text = pyperclip.paste()
            if current_text != last_text:
                cleaned_text = clean_whitespace(current_text)
                if cleaned_text != current_text:
                    pyperclip.copy(cleaned_text)
                    print(f"Cleaned text copied to clipboard: {cleaned_text}")
                last_text = cleaned_text
            time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nStopped monitoring clipboard.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
