"""
ass_generator.py — ASS Subtitle Generator
-----------------------------------------
Converts word-level timestamps into an Advanced Substation Alpha (.ass) file.
Uses pysubs2 for structure and implements Karaoke tags and Safe Margins.
"""

import pysubs2
from pysubs2 import SSAFile, SSAEvent, SSAStyle, Color

def ms_to_cs(ms):
    """Convert milliseconds to centiseconds (10ms units) for ASS karaoke tags."""
    return int(ms / 10)

def generate_ass(word_timestamps: list[dict], output_path: str, video_width=1280, video_height=720):
    """
    word_timestamps: list of {"word": str, "start": float, "end": float}
    where start and end are in SECONDS.
    """
    subs = SSAFile()
    
    # Crucial: Set play resolution headers so margins and font sizes are scaled 1:1 with video pixels
    subs.info["PlayResX"] = video_width
    subs.info["PlayResY"] = video_height
    
    margin = int(video_width * 0.10) # 10% safe zone on left/right
    
    # Main Style
    style = SSAStyle(
        fontname="Roboto",
        fontsize=28,
        primarycolor=Color(255, 215, 0),          # Spoken active color: Gold / Yellow
        secondarycolor=Color(255, 255, 255),      # Unspoken color: White
        backcolor=Color(0, 0, 0, 160),            # Opaque black background box
        borderstyle=3,                            # 3 = Opaque Box
        outline=4,                                # Clean padding around the text inside the box
        shadow=0,
        alignment=2,                              # Bottom Center
        marginl=margin,
        marginr=margin,
        marginv=50                                # 50 pixels vertical margin from bottom
    )
    subs.styles["Default"] = style
    
    # Group words into chunks (sentences or max N words)
    MAX_WORDS_PER_CHUNK = 5
    
    chunks = []
    current_chunk = []
    
    for entry in word_timestamps:
        word = entry["word"]
        # If word ends in punctuation, break chunk after it
        is_end_of_sentence = word.endswith(('.', '!', '?'))
        
        current_chunk.append(entry)
        
        if is_end_of_sentence or len(current_chunk) >= MAX_WORDS_PER_CHUNK:
            chunks.append(current_chunk)
            current_chunk = []
            
    if current_chunk:
        chunks.append(current_chunk)
        
    # Create SSA Events (Lines of subtitles)
    for chunk in chunks:
        if not chunk:
            continue
            
        start_time_ms = int(chunk[0]["start"] * 1000)
        end_time_ms = int(chunk[-1]["end"] * 1000)
        
        # Build the karaoke string
        # We want the text to be muted, then turn yellow when spoken, then stay white.
        # Actually, standard Karaoke {\k} sweeps from secondary to primary.
        # We can just use the {\k} tag which natively creates the "fill" effect.
        
        text_parts = []
        last_end_ms = start_time_ms
        
        for w in chunk:
            w_start = int(w["start"] * 1000)
            w_end = int(w["end"] * 1000)
            
            # Gap before the word is spoken
            gap_cs = ms_to_cs(w_start - last_end_ms)
            if gap_cs > 0:
                text_parts.append(f"{{\\k{gap_cs}}} ")
            else:
                text_parts.append(" ")
                
            # The word itself taking duration
            dur_cs = ms_to_cs(w_end - w_start)
            # Make the active word yellow while filling
            # {\c&H00FFFF&} sets primary color to yellow. {\r} resets it.
            # But {\k} handles the sweep. We will just let {\k} sweep primary (white).
            # If we want a pop of color, we can use {\K} or manual color tags.
            # Let's keep it simple and elegant: sweeping fill.
            
            # {\K} is sweeping karaoke. 
            text_parts.append(f"{{\\K{dur_cs}}}{w['word']}")
            
            last_end_ms = w_end
            
        # Clean up leading space
        line_text = "".join(text_parts).strip()
        
        event = SSAEvent(
            start=start_time_ms,
            end=end_time_ms,
            text=line_text
        )
        subs.append(event)
        
    subs.save(output_path)
    return output_path
