import subprocess
import sys

# Auto-install gTTS if not present
try:
    from gtts import gTTS
except ImportError:
    print("gTTS not installed. Installing it now...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "gTTS"])
    from gtts import gTTS

# Sample meeting dialogue to generate as speech
text = (
    "Hi everyone, let's quickly align on our sprint tasks. "
    "Shubham, you need to complete the payment module API integration by July 25th, 2026. "
    "Vijay, please verify all unit tests pass before the QA handoff on July 28th. "
    "Priya will configure the staging server environment by EOD tomorrow. "
    "Let's make sure our Feishu Base and project group are updated correctly. Thanks team!"
)

output_filename = "sample_meeting.mp3"
print(f"Generating {output_filename} using Google Text-to-Speech...")

try:
    tts = gTTS(text=text, lang="en")
    tts.save(output_filename)
    print(f"Successfully generated {output_filename} in the project folder!")
except Exception as e:
    print(f"Failed to generate audio file: {e}")
