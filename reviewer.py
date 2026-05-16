import re

def stop_words():
    # expanded standard stopwords + common philosophical filler
    stops = "this that the a an and or but if because as what when where how why is are was were be been being have has had do does did will would shall should can could may might must to of in for with on at from by about as into like through after over between out against during without before under around among it its they their them we our us you your very really just too so not no also however thus therefore moreover indeed further furthermore then than such only".split()
    return set(stops)

def extract_ngrams(text, n=2):
    """
    Strips out stop words and extracts overlapping consecutive 'n' length word sequences (n-grams).
    """
    words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', text) if w.lower() not in stop_words()]
    ngrams = set(zip(*[words[i:] for i in range(n)]))
    return ngrams

def get_repetition_penalty(base_text, new_text, n=2):
    """
    Compares new_text against the base_text.
    Returns:
       score: float (0.0 to 1.0) representing the percentage of new_text bigrams that are stolen/recycled from base_text.
       overlapping_phrases: list of string phrases that were reused.
    """
    if not base_text or not new_text:
        return 0.0, []
        
    base_ngrams = extract_ngrams(base_text, n)
    new_ngrams = extract_ngrams(new_text, n)
    
    if not new_ngrams: 
        return 0.0, []
    
    overlap = base_ngrams.intersection(new_ngrams)
    repetition_score = len(overlap) / len(new_ngrams)
    
    overlapping_phrases = [" ".join(gram) for gram in overlap]
    return repetition_score, overlapping_phrases
