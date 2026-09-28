package com.brainuke.serenitydroid.util

/**
 * Utility ensuring strict zero-leakage isolation of model thoughts and internal reasoning tags
 * (<thought>...</thought>, <think>...</think>, <reasoning>...</reasoning>) from public speech output.
 */
object ThoughtIsolator {

    private val thoughtBlockRegex = Regex(
        """(?s)<(?:thought|think|reasoning)>(.*?)</(?:thought|think|reasoning)>|<\|channel\>thought\s*(.*?)(?:<channel\|>|<\|channel\>|$)|<\|think\|\>\s*(.*?)(?:</think>|<\|think\|\>|$)""",
        RegexOption.IGNORE_CASE
    )

    private val orphanStartTagRegex = Regex(
        """(?s)(?:<(?:thought|think|reasoning)>|<\|channel\>thought|<\|think\|\>).*""",
        RegexOption.IGNORE_CASE
    )

    private val rawTagRegex = Regex(
        """</?(?:thought|think|reasoning)>|<\|channel\>thought|<channel\|>|<\|channel\>|<\|think\|>""",
        RegexOption.IGNORE_CASE
    )

    data class IsolatedResult(
        val thought: String,
        val speech: String
    )

    /**
     * Isolates internal thought streams from public speech output.
     * Extracts all reasoning tags into [IsolatedResult.thought] and strips them completely
     * from [IsolatedResult.speech].
     */
    fun isolate(rawThought: String?, rawSpeech: String?): IsolatedResult {
        val thoughts = mutableListOf<String>()

        if (!rawThought.isNullOrBlank()) {
            thoughts.add(cleanThoughtText(rawThought))
        }

        var speechClean = rawSpeech ?: ""

        // Extract complete <thought>...</thought> or Gemma 4 <|channel>thought...<channel|> blocks embedded in speech
        thoughtBlockRegex.findAll(speechClean).forEach { match ->
            val extractedContent = (match.groups[1]?.value
                ?: match.groups[2]?.value
                ?: match.groups[3]?.value
                ?: "").trim()
            if (extractedContent.isNotEmpty()) {
                thoughts.add(cleanThoughtText(extractedContent))
            }
        }
        speechClean = thoughtBlockRegex.replace(speechClean, "").trim()

        // Handle dangling/unclosed <thought> tags (e.g. from incomplete streaming tokens)
        if (orphanStartTagRegex.containsMatchIn(speechClean)) {
            val orphanMatch = orphanStartTagRegex.find(speechClean)
            if (orphanMatch != null) {
                val danglingText = orphanMatch.value.replace(rawTagRegex, "").trim()
                if (danglingText.isNotEmpty()) {
                    thoughts.add(cleanThoughtText(danglingText))
                }
                speechClean = speechClean.substring(0, orphanMatch.range.first).trim()
            }
        }

        // Final sanity clean of any residual tags in speech text
        speechClean = speechClean.replace(rawTagRegex, "").trim()

        val consolidatedThought = thoughts.filter { it.isNotBlank() }
            .distinct()
            .joinToString("\n\n")

        return IsolatedResult(
            thought = consolidatedThought,
            speech = speechClean.ifEmpty { "..." }
        )
    }

    private fun cleanThoughtText(text: String): String {
        return text.replace(rawTagRegex, "").trim()
    }
}
