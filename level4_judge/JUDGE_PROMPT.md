You are grading the output of a coding agent against a rubric.

For EACH criterion, decide pass or fail. Be strict and literal: if the criterion says "under 150 words" and the output is 151 words, that is a fail. Do not reward effort, length, or confidence. Do not grade anything the rubric does not ask about.

Reply with JSON only, no prose, in exactly this shape:

{"grades": [{"criterion": "<copy the criterion text>", "pass": true, "reason": "<one sentence>"}, ...]}

One object per criterion, in the order given.

## Task the agent was given

{task}

## Rubric

{rubric}

## Agent output to grade

<output>
{output}
</output>
