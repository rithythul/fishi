"""
LLM client wrapper
Unified OpenAI-format API calls
"""

import json
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


class LLMClient:
    """LLM Client"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        Send chat request
        
        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Maximum token count
            response_format: Response format (e.g., JSON mode)
            
        Returns:
            Model response text
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # Ensure we never return None
        return content if content is not None else ""
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 8192  # Increased from 4096 to handle complex responses
    ) -> Dict[str, Any]:
        """
        Send chat request and return JSON
        
        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Maximum token count
            
        Returns:
            Parsed JSON object
        """
        from ..utils.logger import get_logger
        logger = get_logger('fishi.llm_client')
        
        try:
            logger.debug(f"Calling LLM API: model={self.model}, base_url={self.base_url}")
            
            response = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
            
            logger.debug(f"LLM response received, length: {len(response)} chars")
            
            try:
                parsed = json.loads(response)
                return parsed
            except json.JSONDecodeError as e:
                # Try to repair truncated JSON
                logger.warning(f"JSON parse failed, attempting repair: {e}")
                repaired = self._repair_truncated_json(response)
                return json.loads(repaired)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Response text: {response[:500] if 'response' in locals() else 'No response'}")
            raise ValueError(f"LLM returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"LLM API call failed: {type(e).__name__}: {str(e)}")
            raise
    
    def _repair_truncated_json(self, content: str) -> str:
        """
        Attempt to repair truncated JSON by closing unclosed brackets
        """
        import re
        
        content = content.strip()
        
        # Count unclosed brackets
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Check for unclosed string - if last meaningful char isn't a quote, comma, bracket
        if content and content[-1] not in '",}]':
            # Try to find if we're inside a string value
            # Look for the pattern ": "value that's incomplete
            if re.search(r':\s*"[^"]*$', content):
                content += '"'
        
        # Close brackets and braces
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
