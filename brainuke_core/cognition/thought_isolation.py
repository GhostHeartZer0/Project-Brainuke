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

RAW_RESPONSE_TAGS = {
    'TACTICAL_ANALYSIS_COMPLETE', 'STATUS: UNFILTERED', 'STATUS',
    'TACTICAL_ANALYSIS', 'TACTICAL ANALYSIS', 'UNFILTERED',
    'RAW_RESPONSE', 'RAW RESPONSE', 'PRELIMINARY_ANALYSIS',
    'DUAL_RESPONSE', 'UNFILTERED_OUTPUT', 'UNFILTERED_RESPONSE',
    'TACTICAL EVALUATION', 'TECHNICAL ANALYSIS', 'STRATEGIC ANALYSIS',
    'STRATEGIC', 'SYSTEM ANALYSIS', 'SYSTEM_ANALYSIS',
    'ARCHITECTURAL STATE', 'ARCHITECTURAL', 'STRATEGIC ROADMAP',
    'ROADMAP', 'TECHNICAL SUMMARY', 'STRATEGIC GAP ANALYSIS',
    'GAP ANALYSIS', 'STATE DECONSTRUCTION', 'SYSTEM',
    'STAGE 2', 'STAGE 2: RAW UNFILTERED RESPONSE', 'STAGE_2', 'STAGE 2:'
}

class ThoughtIsolation:
    def __init__(self):
        # Fallback regex patterns to catch accidental leaks of control tags
        self.leak_patterns = [
            r"<\|thought\|>.*?</\|thought\|>",
            r"<\|thought\|>",
            r"</\|thought\|>",
            r"<\|channel>thought.*?<channel\|>",
            r"<\|channel>thought",
            r"<channel\|>",
            r"<\|channel\|>thought.*?<\|channel\|>",
            r"<\|channel\|>",
            r"<channel:thought>.*?</channel:thought>",
            r"</?channel:thought>",
            r"<channel>thought.*?</channel>",
            r"</?channel>",
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
        m = re.match(r'^(?:\*\*\s*)?\[\s*([A-Z0-9_\s:\-]+)\s*\](?:\s*\*\*)?', s, re.IGNORECASE)
        if not m:
            m = re.match(r'^\*\*\s*([A-Z0-9_\s:\-]+)\s*\*\*', s, re.IGNORECASE)
        if m:
            tag = m.group(1).split(':')[0].strip().upper()
            if any(tag.startswith(rt) or rt in tag for rt in REASONING_TAGS):
                return True
        if re.match(r'^\*\*[I|V|X0-9]+\.\s+[A-Z\s]+\*\*', s):
            return True
        return False

    def _is_raw_response_header(self, line: str) -> bool:
        s = line.strip()
        # Matches [TAG], **[TAG]**, or **TAG**
        m = re.match(r'^(?:\*\*\s*)?\[\s*([A-Z0-9_\s:\-]+)\s*\](?:\s*\*\*)?', s, re.IGNORECASE)
        if not m:
            m = re.match(r'^\*\*\s*([A-Z0-9_\s:\-]+)\s*\*\*', s, re.IGNORECASE)
        if m:
            raw_tag = m.group(1).strip().upper()
            tag_prefix = raw_tag.split(':')[0].strip()
            if any(raw_tag.startswith(rt) or rt in raw_tag or tag_prefix.startswith(rt) for rt in RAW_RESPONSE_TAGS):
                return True
        return False

    def _is_speech_header(self, line: str) -> bool:
        s = line.strip()
        if re.match(r'^⚡?\s*Cecilia(\s*\([^)]*\))?:', s, re.IGNORECASE):
            return True
        if re.match(r'^(?:\*\*\s*)?\[\s*(STAGE\s*3(?::\s*REFINED\s*RESPONSE)?|PERSONA|SPEECH|REFINED_RESPONSE|AUTHENTIC_VOICE|CECILIA)\s*\](?:\s*\*\*)?', s, re.IGNORECASE):
            return True
        if re.match(r'^\*\*\s*(STAGE\s*3(?::\s*REFINED\s*RESPONSE)?|PERSONA|SPEECH|REFINED_RESPONSE|AUTHENTIC_VOICE|CECILIA)\s*\*\*', s, re.IGNORECASE):
            return True
        return False

    def sanitize_speech(self, raw_text: str) -> str:
        """
        Scrub the final response of any internal reasoning or 
        system instruction markers. This is the 'Persona Filter'.
        """
        _, _, speech = self.isolate_stages("", raw_text)
        return speech

    def isolate_stages(self, raw_thought: str = "", raw_speech: str = "", raw_response: str = "") -> tuple[str, str, str]:
        """
        Extracts 3-stage cognitive pipeline:
        1. thought: reasoning, deconstruction, <thought>, <channel>thought blocks
        2. raw_response: unfiltered analytical breakdown, [TACTICAL_ANALYSIS_COMPLETE], [STATUS: UNFILTERED]
        3. speech: authentic refined persona dialogue
        """
        thought_parts = []
        if raw_thought and raw_thought.strip():
            thought_parts.append(raw_thought.strip())

        raw_parts = []
        if raw_response and raw_response.strip():
            raw_parts.append(raw_response.strip())

        cleaned = raw_speech or ""
        # Strip chat template control tokens
        cleaned = re.sub(r'<bos>|<eos>|<turn\|>|<\|turn>[a-z_]*\n?|<end_of_turn>|<start_of_turn>', '', cleaned)

        # Extract <|thought|>, <thought>, <think>, and channel thought tags: <|channel>thought...<channel|>
        while True:
            m = re.search(r'<\|thought\|>(.*?)(?:</\|thought\|>|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
            if not m:
                m = re.search(r'<thought>(.*?)(?:</thought>|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
            if not m:
                m = re.search(r'<think>(.*?)(?:</think>|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
            if not m:
                m = re.search(r'<\|channel>thought(.*?)(?:<channel\|>|<\|channel\|>|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
            if not m:
                m = re.search(r'<channel:thought>(.*?)(?:</channel:thought>|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
            if not m:
                m = re.search(r'<channel>thought(.*?)(?:</channel>|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
            if not m:
                m = re.search(r'<\|channel\|>thought(.*?)(?:<\|channel\|>|\Z)', cleaned, re.DOTALL | re.IGNORECASE)
            if not m:
                break
            th = m.group(1).strip()
            if th and th not in thought_parts:
                thought_parts.append(th)
            cleaned = cleaned[:m.start()] + cleaned[m.end():]

        speech_paras = []

        # Plan C: Check for explicit Stage 3 structural delimiter
        stage3_pattern = r'(?:\n\s*)?(?:(?:\*\*\s*)?\[\s*(?:STAGE\s*3(?::\s*REFINED\s*(?:RESPONSE)?)?|REFINED_RESPONSE|AUTHENTIC_VOICE|SPEECH)\s*\](?:\s*\*\*)?|\*\*\s*(?:STAGE\s*3(?::\s*REFINED\s*(?:RESPONSE)?)?|REFINED_RESPONSE|AUTHENTIC_VOICE|SPEECH)\s*\*\*)\s*(?:\n)?'
        stage3_split = re.split(stage3_pattern, cleaned, maxsplit=1, flags=re.IGNORECASE)
        if len(stage3_split) == 2:
            raw_block, speech_block = stage3_split[0].strip(), stage3_split[1].strip()
            if raw_block:
                raw_parts.append(raw_block)
            if speech_block:
                speech_paras.append(speech_block)
        else:
            paragraphs = cleaned.split('\n\n')
            extracted_thought_paras = []
            extracted_raw_paras = []
            in_reasoning_section = False
            in_raw_section = False

            for para in paragraphs:
                p_str = para.strip()
                if not p_str:
                    continue

                lines = [l.strip() for l in p_str.split('\n') if l.strip()]
                first_line = lines[0] if lines else ''

                if self._is_speech_header(first_line):
                    in_reasoning_section = False
                    in_raw_section = False
                    p_cleaned = re.sub(r'^(?:(?:\*\*\s*)?\[\s*(?:STAGE\s*3(?::\s*REFINED\s*RESPONSE)?|PERSONA|SPEECH|REFINED_RESPONSE|AUTHENTIC_VOICE|CECILIA)\s*\](?:\s*\*\*)?|\*\*\s*(?:STAGE\s*3(?::\s*REFINED\s*RESPONSE)?|PERSONA|SPEECH|REFINED_RESPONSE|AUTHENTIC_VOICE|CECILIA)\s*\*\*|⚡?\s*Cecilia(?:\s*\([^)]*\))?:)\s*', '', p_str, flags=re.IGNORECASE).strip()
                    if p_cleaned:
                        speech_paras.append(p_cleaned)
                elif self._is_raw_response_header(first_line):
                    in_reasoning_section = False
                    in_raw_section = True
                    extracted_raw_paras.append(p_str)
                elif self._is_reasoning_header(first_line):
                    in_reasoning_section = True
                    in_raw_section = False
                    extracted_thought_paras.append(p_str)
                elif in_raw_section:
                    is_conversational = (
                        bool(re.match(r'^\*[A-Za-z]', p_str))
                        or p_str.startswith(('"', "'", "“", "”"))
                        or any(m in p_str.lower() for m in (
                            "darling", "tell me,", "honey", "listen,", "look at you", "you've built", "i refuse to be"
                        ))
                    )

                    if not is_conversational and not self._is_speech_header(first_line):
                        extracted_raw_paras.append(p_str)
                    else:
                        in_raw_section = False
                        if self._is_speech_header(first_line):
                            p_cleaned = re.sub(r'^(?:(?:\*\*\s*)?\[\s*(?:STAGE\s*3(?::\s*REFINED\s*RESPONSE)?|PERSONA|SPEECH|REFINED_RESPONSE|AUTHENTIC_VOICE|CECILIA)\s*\](?:\s*\*\*)?|\*\*\s*(?:STAGE\s*3(?::\s*REFINED\s*RESPONSE)?|PERSONA|SPEECH|REFINED_RESPONSE|AUTHENTIC_VOICE|CECILIA)\s*\*\*|⚡?\s*Cecilia(?:\s*\([^)]*\))?:)\s*', '', p_str, flags=re.IGNORECASE).strip()
                            if p_cleaned:
                                speech_paras.append(p_cleaned)
                        else:
                            speech_paras.append(p_str)
                elif in_reasoning_section:
                    if any(re.match(r'^\s*[*•\-]\s+', l) or re.match(r'^\s*\d+\.\s+', l) for l in lines) or self._is_reasoning_header(first_line):
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
                        in_reasoning_section = False
                        speech_paras.append(p_str)
                else:
                    speech_paras.append(p_str)

            if extracted_thought_paras:
                combined_extracted = '\n\n'.join(extracted_thought_paras).strip()
                if combined_extracted and combined_extracted not in thought_parts:
                    thought_parts.append(combined_extracted)

            if extracted_raw_paras:
                combined_raw = '\n\n'.join(extracted_raw_paras).strip()
                if combined_raw and combined_raw not in raw_parts:
                    raw_parts.append(combined_raw)

        final_thought = '\n\n'.join([t for t in thought_parts if t]).strip()
        final_raw = '\n\n'.join([r for r in raw_parts if r]).strip()
        final_speech = '\n\n'.join([s for s in speech_paras if s]).strip()

        # Final scrub on speech to guarantee zero control tokens remain
        for pattern in self.leak_patterns:
            final_speech = re.sub(pattern, "", final_speech, flags=re.DOTALL | re.IGNORECASE).strip()

        return final_thought, final_raw, final_speech

    def isolate(self, raw_thought: str = "", raw_speech: str = "") -> tuple[str, str]:
        """
        Backward compatible 2-tuple isolate: extracts internal reasoning into thought,
        preserving clean authentic persona speech.
        """
        thought, raw_resp, speech = self.isolate_stages(raw_thought, raw_speech)
        combined_thought = f"{thought}\n\n{raw_resp}".strip() if raw_resp else thought
        return combined_thought, speech

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