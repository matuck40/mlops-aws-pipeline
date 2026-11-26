"""API na Lambda: o Mangum traduz eventos do API Gateway (HTTP API) para o FastAPI.

Módulo próprio para não carregar o ETL (nem o `requests`) no cold start da API.
O armazenamento é aberto na importação: a Lambda reaproveita o container entre
requisições, então isso roda uma vez por container, não por chamada.
"""

from mangum import Mangum

from volt.api import criar_app
from volt.armazenamento import abrir_armazenamento

# lifespan="off": a API não tem eventos de startup/shutdown
handler = Mangum(criar_app(abrir_armazenamento()), lifespan="off")
