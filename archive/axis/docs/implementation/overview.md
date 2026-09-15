# Implementation Overview

## Purpose

본 문서는 Axis 시스템의 실제 구현 구조를 개괄적으로 설명한다.
이 문서는 설계 원칙이나 운영 규칙을 정의하지 않으며,
현재 구현이 어떤 가정을 따르고 있는지만을 설명한다.

## High-Level Flow

현재 구현은 다음 기본 흐름을 따른다.

External Input
→ Synapse (collection & pre-processing)
→ Neuron (compute)
→ Cortex (aggregation, optional)
→ Engram (persistence, optional)

각 단계는 독립적으로 실행되며,
실행 결과는 다음 단계를 강제하지 않는다.

## Execution Characteristics

- 모든 실행은 짧게 끝나며 즉시 종료된다
- 실행 간 상태는 공유되지 않는다
- 실패는 예외가 아니라 기록이다

## Notes

본 구현은 변경 가능하며,
구현 변경은 상위 문서의 규칙을 변경하지 않는다.

