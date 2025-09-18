#!/usr/bin/env python3
"""
Transcript Cleanup Script
Cleans up Salesforce conversation transcripts by:
1. Removing "Move the player to X seconds" lines
2. Reformatting to: MM:SS - Speaker Name - [Tags]: utterance
"""

import sys
import re


def clean_transcript(input_file, output_file):
    """
    Clean up the transcript from input_file and write to output_file.
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    cleaned_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        # Skip line numbers (just digits followed by →)
        if re.match(r'^\d+→', line):
            # Extract the content after the arrow
            line = line.split('→', 1)[1] if '→' in line else ''
            if not line:
                i += 1
                continue
        
        # Skip "Move the player to X seconds in the call" lines
        if "Move the player to" in line and "seconds in the call" in line:
            i += 1
            continue
        
        # Check if this looks like a speaker name (not a timestamp and not all lowercase)
        # Speaker names are typically proper names or "Speaker"
        if line and not re.match(r'^\d{2}:\d{2}', line) and line[0].isupper():
            speaker = line
            
            # Look for timestamp on next line
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # Remove line number if present
                if re.match(r'^\d+→', next_line):
                    next_line = next_line.split('→', 1)[1].strip() if '→' in next_line else ''
                
                # Check if it's a timestamp
                if re.match(r'^\d{2}:\d{2}$', next_line):
                    timestamp = next_line
                    i += 2
                    
                    # Collect the utterance and any tags
                    tags = []
                    utterance_parts = []
                    
                    while i < len(lines):
                        current_line = lines[i].strip()
                        
                        # Remove line number if present
                        if re.match(r'^\d+→', current_line):
                            current_line = current_line.split('→', 1)[1].strip() if '→' in current_line else ''
                        
                        # Stop if we hit the next speaker or "Move the player" line
                        if not current_line:
                            break
                        if "Move the player to" in current_line:
                            break
                        # Check if it's a new speaker (uppercase first letter, not a tag)
                        if current_line and current_line[0].isupper() and not current_line.startswith(('Question', 'Longest', 'Next')):
                            # Check if next line is a timestamp
                            if i + 1 < len(lines):
                                peek_line = lines[i + 1].strip()
                                if re.match(r'^\d+→', peek_line):
                                    peek_line = peek_line.split('→', 1)[1].strip() if '→' in peek_line else ''
                                if re.match(r'^\d{2}:\d{2}$', peek_line):
                                    break
                        
                        # Check if this line is a tag
                        if current_line in ['Question', 'Longest Customer Story', 'Longest Monologue', 
                                           'Next Steps', 'Longest MonologueNext Steps']:
                            tags.append(current_line)
                        else:
                            # It's part of the utterance
                            utterance_parts.append(current_line)
                        
                        i += 1
                    
                    # Combine utterance parts
                    utterance = ' '.join(utterance_parts).strip()
                    
                    # Format the output
                    if utterance:  # Only output if there's actual content
                        if tags:
                            # Combine tags with commas
                            tag_str = ', '.join(tags)
                            output_line = f"{timestamp} - {speaker} - [{tag_str}]: {utterance}"
                        else:
                            output_line = f"{timestamp} - {speaker}: {utterance}"
                        
                        cleaned_lines.append(output_line)
                    
                    continue
        
        i += 1
    
    # Write the cleaned transcript
    with open(output_file, 'w', encoding='utf-8') as f:
        for line in cleaned_lines:
            f.write(line + '\n')
    
    print(f"Transcript cleaned successfully!")
    print(f"Input: {input_file}")
    print(f"Output: {output_file}")
    print(f"Total utterances: {len(cleaned_lines)}")


def main():
    if len(sys.argv) != 3:
        print("Usage: python cleanup_transcript.py <input_file> <output_file>")
        print("Example: python cleanup_transcript.py transcripts/ex1.txt transcripts/ex1_cleaned.txt")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    try:
        clean_transcript(input_file, output_file)
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()