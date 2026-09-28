"""
Enforces strict separation between internal reasoning and external persona.
"""

import re

REASONING_TAGS = {
    'DECONSTRUCTION', 'MOTIVE', 'SUBTEXT', 'STRATEGIC IMPLICATIONS',
    'COGNITIVE PIVOT', 'THE CONTRAST HEURISTIC', 'FUNCTIONAL GOAL',
    'INPUT DECONSTRUCTION', 'SYNTACTIC STRUCTURE', 'LINGUISTIC PROFILE',
    'CONTEXTUAL VOID', 'REASONING ENGINE', 'ANALYSIS_START', 'ANALYSIS_END',
    'INTERNAL_THOUGHT', 'THOUGHT_START', 'THOUGHT_END',
    'INTENT GUARDRAIL TRIGGERED', 'SYSTEM INSTRUCTION', 'SYSTEM DIRECTIVE',
    'DMN ANALYTICAL CONCEPTS', 'GROUNDED WORLDVIEW', 'PARAM'
}

class ThoughtIsolation:
    def __init__(self):
        # Fallback regex patterns to catch accidental leaks of control tags
        self.leak_patterns = [
            r"<\|thought\|>.*?</\|thought\|>",
            r"<\|thought\|>",
            r"</\|thought\|>",
            r"<\|channel>thought.*?<channel\|>",
            r"<thought>.*?</thought>",
            r"</?thought>",
            r"</?think>",
            r"<start_of_turn>.*?</start_of_turn>",
            r"<start_of_turn>",
            r"<end_of_turn>",
            r"<\|turn>[a-z_]*\n?",
            r"<turn\|>",
            r"</turn>",
            r"<bos>",
            r"<eos>",
        ]

    def _is_reasoning_header(self, line: str) -> bool:
        s = line.strip()
        m = re.match(r'^\[([A-Z0-9_\s:]+)\]', s, re.IGNORECASE)
        if m:
            tag = m.group(1).split(':')[0].strip().upper()
            if any(tag.startswith(rt) or rt in tag for rt in REASONING_TAGS):
                return True
        if re.match(r'^\*\*[I|V|X0-9]+\.\s+[A-Z\s]+\*\*', s):
            return True
        return False

    def sanitize_speech(self, raw_text: str) -> str:
        """
        Scrub the final response of any internal reasoning or 
        system instruction markers. This is the 'Persona Filter'.
        """
        _, speech = self.isolate("", raw_text)
        return speech

    def isolate(self, raw_thought: str = "", raw_speech: str = "") -> tuple[str, str]:
        """
        Extracts any reasoning or deconstruction blocks embedded in speech into thought,
        ensuring speech is 100% clean authentic voice hidden from internal reasoning.
        """
        thought_parts = []
        if raw_thought and raw_thought.strip():
            thought_parts.append(raw_thought.strip())

        cleaned = raw_speech or ""
        # Strip chat template control tokens
        cleaned = re.sub(r'<bos>|<eos>|<turn\|>|<\|turn>[a-z_]*\n?|<end_of_turn>|<start_of_turn>', '', cleaned)

        # Extract <|thought|> ... </|thought|> and <thought> ... </thought>
        while True:
            m = re.search(r'<\|thought\|>(.*?)(?:</\|thought\|>|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
            if not m:
                m = re.search(r'<thought>(.*?)(?:</thought>|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
            if not m:
                m = re.search(r'<think>(.*?)(?:</think>|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
            if not m:
                break
            th = m.group(1).strip()
            if th and th not in thought_parts:
                thought_parts.append(th)
            cleaned = cleaned[:m.start()] + cleaned[m.end():]

        paragraphs = cleaned.split('\n\n')
        extracted_thought_paras = []
        speech_paras = []
        in_reasoning_section = False

        for para in paragraphs:
            p_str = para.strip()
            if not p_str:
                continue

            lines = [l.strip() for l in p_str.split('\n') if l.strip()]
            first_line = lines[0] if lines else ''

            if self._is_reasoning_header(first_line):
                in_reasoning_section = True
                extracted_thought_paras.append(p_str)
            elif in_reasoning_section:
                # Bullet points or analytical statements under reasoning section
                if any(l.startswith(('*', '-', '•', '**')) for l in lines):
                    extracted_thought_paras.append(p_str)
                elif self._is_reasoning_header(first_line):
                    extracted_thought_paras.append(p_str)
                elif any(phrase in p_str.lower() for phrase in [
                    'the subject', 'the user', 'cognitive pivot', 'heuristic',
                    'behavioral activation', 'dialectical', 'primary objective',
                    'traditional optimism', 'kinetic output', 'contextual void',
                    'semantic unit', 'syntactic structure', 'linguistic profile'
                ]):
                    extracted_thought_paras.append(p_str)
                elif any(term in first_line.lower() for term in [
                    'consequently', 'furthermore', 'additionally', 'in contrast',
                    'moreover', 'the contrast', 'functional goal'
                ]):
                    extracted_thought_paras.append(p_str)
                else:
                    # Spoken persona dialogue starts here
                    in_reasoning_section = False
                    speech_paras.append(p_str)
            else:
                speech_paras.append(p_str)

        if extracted_thought_paras:
            combined_extracted = '\n\n'.join(extracted_thought_paras).strip()
            if combined_extracted and combined_extracted not in thought_parts:
                thought_parts.append(combined_extracted)

        final_thought = '\n\n'.join([t for t in thought_parts if t]).strip()
        final_speech = '\n\n'.join([s for s in speech_paras if s]).strip()

        # Final scrub on speech to guarantee zero control tokens remain
        for pattern in self.leak_patterns:
            final_speech = re.sub(pattern, "", final_speech, flags=re.DOTALL | re.IGNORECASE).strip()

        return final_thought, final_speech

    def validate_isolation(self, thought: str, speech: str) -> bool:
        """
        A diagnostic check to ensure the speech doesn't contain 
        significant chunks of the thought process.
        """
        if len(thought) > 0 and len(speech) > 0:
            overlap = set(thought.split()) & set(speech.split())
            if len(overlap) / len(speech.split()) > 0.5:
                return False
        return True