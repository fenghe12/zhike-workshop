"""Qwen API client"""
import uuid, requests, json, os

class QwenClient:
    def __init__(self, model='kivy-qwen3_6-plus', base_url='http://api-hub.inner.chj.cloud/llm-gateway/v1', token=None):
        self.model = model
        self.base_url = base_url
        self.token = token or os.environ.get('QWEN_API_TOKEN')
        if not self.token:
            raise ValueError('QWEN_API_TOKEN not set')

    def chat(self, messages, max_tokens=4096, temperature=0.2, enable_thinking=False, timeout=60):
        url = f'{self.base_url}/chat/completions/{self.model}'
        headers = {
            'Content-Type': 'application/json',
            'BCS-APIHub-RequestId': str(uuid.uuid4()),
            'X-CHJ-GWToken': self.token,
        }
        data = {
            'model': self.model,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'enable_thinking': enable_thinking,
            'messages': messages,
        }
        resp = requests.post(url, headers=headers, json=data, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()
        return result.get('choices', [{}])[0].get('message', {}).get('content', '')

    def translate(self, text, target_language='English', source_language='Chinese'):
        system_prompt = f'You are a professional translator. Translate the following {source_language} text to {target_language}. Maintain the original meaning, tone, and formatting. Only return the translated text, without explanations.'
        return self.chat([{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': text}])

    def back_translate(self, text, original_language='Chinese', target_language='English'):
        system_prompt = f'You are a professional translator. Translate the following {target_language} text back to {original_language}. Only return the translated text, without explanations.'
        return self.chat([{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': text}])

    def semantic_judge(self, original_text, back_translated_text):
        system_prompt = 'You are a translation quality evaluator. Compare the original text and the back-translated text. Respond with exactly one word: CONSISTENT or INCONSISTENT.'
        user_prompt = f'Original: {original_text}\nBack-translated: {back_translated_text}'
        result = self.chat([{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}], max_tokens=10, temperature=0.0)
        return 'CONSISTENT' in result.upper()
