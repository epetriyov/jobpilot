"""Use case ScoreVacancy: скоринг новых вакансий (DOMAIN.md §3.2, R1–R3, R5).

R1 — только вакансии без актуального скора текущей prompt_version (выборка unscored);
R2 — невалидный выход LLM после 1 ретрая пропускает вакансию, пайплайн жив;
R3 — few-shot из последних размеченных; R5 — текст уходит data-блоком (в адаптере).
"""

from __future__ import annotations

import structlog

from app.application.fewshot import FewShotSelectorPort, RecentSelector, vacancy_text
from app.domain.relevance import LlmScore, Score
from app.domain.shared import PromptVersion
from app.ports.llm import LlmPort
from app.ports.repositories import LabelRepositoryPort, ScoringRepositoryPort

log = structlog.get_logger("application.score_vacancy")


class ScoreVacancy:
    def __init__(
        self,
        *,
        llm: LlmPort,
        seen_repo: ScoringRepositoryPort,
        label_repo: LabelRepositoryPort,
        system_prompt: str,
        prompt_version: PromptVersion,
        model_name: str,
        fewshot_limit: int = 10,
        fewshot_text_limit: int = 800,
        selector: FewShotSelectorPort | None = None,
    ) -> None:
        self._llm = llm
        self._seen = seen_repo
        self._labels = label_repo
        self._system_prompt = system_prompt
        self._prompt_version = prompt_version
        self._model_name = model_name
        self._fewshot_limit = fewshot_limit
        self._fewshot_text_limit = fewshot_text_limit
        # дефолт — «последние N» (R3); semantic инъектируется композицией по конфигу
        self._selector: FewShotSelectorPort = selector or RecentSelector(
            label_repo, limit=fewshot_limit, text_limit=fewshot_text_limit
        )

    async def score_pending(self, limit: int = 200) -> int:
        """Скорит все ждущие вакансии; возвращает число успешно скоренных."""
        pending = await self._seen.unscored(self._prompt_version.as_str(), limit)
        log.info("scoring_start", pending=len(pending))

        scored = 0
        for snapshot in pending:
            few_shot = await self._selector.select_for(snapshot)
            llm_score = await self._llm.complete(
                purpose="scoring",
                prompt_version=self._prompt_version,
                system=self._system_prompt,
                data=vacancy_text(snapshot),
                response_model=LlmScore,
                few_shot=few_shot,
            )
            if llm_score is None:
                # R2: warning уже залогирован адаптером; вакансия остаётся unscored
                log.warning("vacancy_score_skipped", source_ref=snapshot.source_ref.as_key())
                continue
            await self._seen.save_score(
                snapshot.source_ref,
                Score(
                    value=llm_score.score,
                    reason=llm_score.to_reason(),  # обрезка до 200 (R2, многословность ≠ skip)
                    prompt_version=self._prompt_version.as_str(),
                    model=self._model_name,
                ),
            )
            scored += 1

        log.info("scoring_finish", scored=scored, skipped=len(pending) - scored)
        return scored
