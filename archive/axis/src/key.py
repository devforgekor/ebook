from typing import Literal


Plane = Literal["oci", "azure"]
Component = Literal["collector", "model", "runtime"]


def normalize(value: str) -> str:
    """
    error_signature key에 들어가기 전 마지막 정규화 단계.
    - 소문자
    - 공백/대체 불필요한 문자 제거는 호출부 책임
    """
    return value.strip().lower()


def build_error_signature_key(
    plane: Plane,
    component: Component,
    source_or_model: str,
    error_type: str,
) -> str:
    """
    error_signature key 생성

    형식:
      <plane>.<component>.<source_or_model>.<error_type>

    예:
      oci.collector.cnn.timeout
      azure.model.phi.empty
      azure.runtime.execution.oom
    """

    plane_n = normalize(plane)
    component_n = normalize(component)
    subject_n = normalize(source_or_model)
    error_n = normalize(error_type)

    return f"{plane_n}.{component_n}.{subject_n}.{error_n}"
