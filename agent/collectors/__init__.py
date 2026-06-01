"""자원별 사용률 수집기.

한 파일이 한 자원만 다룬다(cpu/memory/net/gpu). 각 수집기는 0~100 사이의
사용률(%)을 반환하며, gpu는 물리 GPU가 없으면 None을 반환할 수 있다.
반환 계약(필드·단위)의 단일 출처는 diagram-and-docs/serverpool-spec.html 이다.
"""
