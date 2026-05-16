import logging
from ddgs import DDGS
from scrapling import Fetcher

def get_web_context(topic: str) -> str:
    """
    Returns search snippets from DuckDuckGo for the given topic, 
    AND performs a full scrape of the #1 result using Scrapling for deep fact-checking.
    """
    try:
        # DDGS API request
        results = DDGS().text(topic, max_results=5)
        
        # Generator outputs list of dicts. If empty or None, fallback.
        if not results:
            return "No web context found."
            
        context = "RECENT NEWS & OPINIONS:\n"
        for i, r in enumerate(results):
            context += f"Result {i+1} ({r.get('title')}): {r.get('body')}\n"
            
        # Apply Scrapling Fact-Check sequence for the #1 result
        top_url = results[0].get('href')
        if top_url:
            try:
                page = Fetcher.get(top_url)
                # Parse all <p> text elements to get the core article body
                paragraphs = page.css('p::text').getall()
                article_text = " ".join([p.strip() for p in paragraphs if len(p.strip()) > 30])
                if article_text:
                    context += f"\nDEEP FACT-CHECK EXCERPT from {top_url}:\n{article_text[:2000]}...\n"
            except Exception as e:
                logging.error(f"Scrapling failed to fetch fact-check URL {top_url}: {e}")
                
        return context
    except Exception as e:
        logging.error(f"Web research failed: {e}")
        return f"Web research unavailable. Rely on internal knowledge. Error: {e}"
