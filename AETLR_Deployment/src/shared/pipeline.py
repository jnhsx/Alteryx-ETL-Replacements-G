from dataclasses import dataclass, field


@dataclass(frozen=True)
class PipelineArtifact:
    output_bytes: bytes
    output_filename: str
    content_type: str
    is_primary: bool = False


@dataclass(frozen=True)
class PipelineResult:
    output_bytes: bytes
    output_filename: str
    content_type: str
    row_count: int | None = None
    warnings: list[str] = field(default_factory=list)
    artifacts: list[PipelineArtifact] = field(default_factory=list)
