# Vértice PDF

Editor de PDF para desktop (Python + PySide6 + PyMuPDF), com tema escuro.
Código 100% original — apenas a lista de funcionalidades foi inspirada no print.

## Rodar
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py            # ou: python main.py arquivo.pdf
```

## Interface (v1.3)
- **Tela inicial:** recentes com miniatura no topo (6 mais recentes + "Ver todos"), ferramentas agrupadas por tarefa, dica de arrastar e soltar.
- **Visualizador:** barra superior enxuta (painel, salvar, desfazer, imprimir, navegação, busca), **barra lateral de ferramentas** só com ícones (dicas ao passar o mouse; rola em janelas baixas), **barra de propriedades contextual** (mostra só tamanho/cor/espessura da ferramenta ativa), barra de status com zoom e avisos rápidos (toast).
- **Arrastar e soltar** PDFs sobre a janela mostra uma área de destino.

## Funcionalidades
| Ferramenta | O que faz |
|---|---|
| Abrir / abas | Várias abas, arrastar e soltar, senha, recentes, busca (Ctrl+F), zoom (Ctrl+roda), painel de miniaturas e marcadores (F4), selecionar e copiar texto **entre páginas** (Ctrl+C, Ctrl+A) |
| Editar PDF | **Editar por palavra** (clique em uma palavra: o parágrafo é emoldurado e só ela é trocada, com barra de fonte/tamanho/B/I/cor; o resto da linha acompanha), **Editar parágrafo** (reflow, fonte original reaproveitada quando possível, tamanho, negrito/itálico, cor, alinhamento), adicionar texto, realçar, apagar área, assinatura desenhada, desfazer |
| Anotações | Seta, linha, retângulo, elipse, caneta, nota (comentário), caixa de texto, carimbos (APROVADO, URGENTE, data…); botão direito sobre uma anotação: editar/excluir |
| Assinatura digital | Assinar com certificado `.pfx/.p12` (visível ou invisível, várias assinaturas), verificar integridade/emissor, criar certificado de teste |
| OCR | Gera PDF pesquisável (requer Tesseract) |
| Lote | Combinar, dividir (por página / N / intervalos), comprimir, converter (PNG/JPG/TXT) |
| Comprimir | 3 níveis; nunca devolve arquivo maior que o original |
| Criar PDF | Página em branco (A4, Carta…) ou a partir de imagens |
| Imprimir | Diálogo nativo com intervalo de páginas |
| Organizar | Arrastar para reordenar, girar, duplicar, excluir, inserir de outro PDF |
| Criptografar | AES-256 com permissões; remover senha |
| Formulário | Preenche campos AcroForm; assinatura desenhada ou por imagem |

## OCR no Windows
1. Instale o Tesseract (build UB Mannheim): https://github.com/UB-Mannheim/tesseract/wiki
2. Marque o idioma **Portuguese** durante a instalação.
3. O app procura em `C:\Program Files\Tesseract-OCR` automaticamente.

## Gerar o .exe e o instalador
Execute `build_exe.bat`. Ele gera o ícone, a pasta `dist\VerticePDF` e, se o
[Inno Setup 6](https://jrsoftware.org/isdl.php) estiver instalado, o instalador
`installer\VerticePDF-Setup.exe` (atalhos, desinstalador e opção de abrir .pdf com o Vértice PDF).
Para um instalador mais confiável no Windows, assine o `.exe` com um certificado de code signing.

## Testes
`pip install pytest` e `pytest -q` (testes do motor de PDF em `tests/`).

## Diagnóstico
Erros inesperados são gravados em `%APPDATA%\VerticePDF\VerticePDF\verticepdf.log` (veja em "Sobre").

## Licença — importante
O PyMuPDF é **AGPL-3.0** (ou licença comercial da Artifex). Para uso pessoal tudo bem;
para **distribuir/vender**, ou publique seu código sob AGPL, ou compre a licença comercial,
ou troque por `pypdfium2` + `pypdf` (menos recursos de edição).

## Limitações conhecidas
- **Editar parágrafo** aplica um único estilo ao parágrafo inteiro (misturas de negrito/cor viram uma só).
- **Editar por palavra** não funciona em páginas giradas nem em texto vertical (cai no editor de parágrafo); se a linha passar da margem da página a troca é recusada.
  A fonte original só é reaproveitada se estiver embutida *com todos os glifos necessários* ou instalada no
  Windows; senão usa-se Helvetica/Times/Courier e o app avisa. O fundo é amostrado da página (bom em fundos lisos;
  evite fundos com imagem/degradê). Se o texto novo não couber, a edição é desfeita com um aviso.
- **Assinatura digital:** a validade jurídica depende do certificado. Certificados autoassinados garantem
  integridade, mas aparecem como "emissor não verificado". Certificados de ICP-Brasil (A1/.pfx) funcionam;
  tokens/cartões A3 (PKCS#11) ainda não são suportados. Não há carimbo de tempo (TSA) nem checagem de revogação (LTV).
  Editar um PDF assinado e salvar **invalida** a assinatura (o app avisa antes).
- Seleção de texto: PDFs digitalizados não têm texto — rode o OCR primeiro.
- Texto adicionado em páginas giradas pode ficar fora de posição.
- Páginas digitalizadas não têm texto editável: rode o OCR antes.

## Tamanho e velocidade (v1.5.2)
- O pacote exclui módulos Qt não usados (WebEngine, QML, Multimídia, 3D, Rede…), o modelo de layout do PyMuPDF e bibliotecas científicas, além de compilar o Python com `optimize=2`. Na compilação de teste em Linux a pasta caiu de ~443 MB para ~284 MB.
- A abertura ficou mais rápida: o módulo de impressão só é carregado ao imprimir e o índice de fontes só ao editar texto.
- O OCR é um componente opcional do instalador (desmarque para baixar menos).

## Nova barra de ferramentas (v1.6.0)
O visualizador agora tem abas no topo: **Visualizar · Editar · Converter · Anotar · Página · Proteger**, cada uma com seus botões
(ícone + nome). Novidades: *Adicionar imagem*, girar/inserir/excluir página direto no documento aberto, e atalhos para OCR,
comprimir, converter, dividir/mesclar e criptografar/descriptografar já com o arquivo atual preenchido.

## Novidades da v1.7.0
- **Edição por palavra validada em PDFs reais** (Chrome, LibreOffice, wkhtmltopdf, ReportLab — `tests/data`): todas as palavras
  de cada documento são trocadas em teste automático. Novo: a troca é recusada se invadir a coluna/célula ao lado, e datas e
  números (`15/03/2026`, `1.234,56`) agora são editáveis como uma palavra.
- **Recuperação automática:** a cada 45 s as alterações não salvas são guardadas em `%APPDATA%\VerticePDF\recovery`; ao abrir
  depois de um travamento o programa oferece recuperar.
- **Janela única:** abrir outro PDF pelo Explorer abre uma nova aba na janela já aberta.
- **Refazer** (`Ctrl+Y` / `Ctrl+Shift+Z`) e histórico de até 40 passos (limitado a 300 MB de memória).
- **Editar:** localizar e substituir (`Ctrl+H`, mantém fonte/tamanho/cor), marca d'água, cabeçalho e rodapé, número de página.
- **Página:** recortar, extrair para novo PDF, inserir páginas de outro PDF. **Proteger:** limpar metadados.
- **Tema escuro / claro / seguir o sistema** (menu ≡ no canto superior direito › Aparência).
- **Teste de instalação no Windows** (`scripts/install_smoke.ps1`, executado pelo GitHub Actions): instala em silêncio, roda o
  autoteste do programa instalado, testa a janela única e desinstala.

## Visual "Central de documentos" (v1.9.0)

Página inicial redesenhada conforme o mockup: sidebar branca com navegação (Início, Recentes, Ferramentas,
Processamento em lote), busca com atalho Ctrl+K (filtra ferramentas e arquivos recentes), zona de abrir/arrastar
PDF, cartões de recentes com miniatura, filtros por grupo de ferramentas e novo cartão "Compartilhar PDF".
Barra de abas com 44 px e paleta clara/escura atualizada. A fonte Geist é usada se estiver instalada
(senão Segoe UI).

## Atualização pelo próprio programa (v1.8.0)
**Para o usuário:** menu ≡ › *Verificar atualizações…* (uma vez por dia o programa também checa sozinho e avisa na barra
inferior). Ao clicar em *Atualizar agora* ele baixa o instalador novo, confere o SHA-256, pergunta se quer salvar o que está
aberto, fecha, instala **por cima** (mesma pasta, mesmas opções, mesma associação de .pdf) e reabre sozinho. Documentos,
configurações, recentes e cópias de recuperação ficam em `%APPDATA%\VerticePDF` e não são tocados.

**Para quem publica:**
1. Em `version.py`, preencha `UPDATE_URL` com a API do seu repositório, por exemplo
   `https://api.github.com/repos/SEU-USUARIO/SEU-REPOSITORIO/releases/latest`
   (ou use um JSON próprio: `{"version": "1.9.0", "url": "https://…/VerticePDF-Setup-1.9.0.exe", "sha256": "…", "notes": "…"}`).
2. Aumente `__version__`, faça commit e crie a tag `v1.9.0`. O workflow *Gerar instalador* compila, testa a instalação e
   publica na *Release* o `VerticePDF-Setup-1.9.0.exe` e o `.sha256`.
3. Quem tem o programa instalado recebe o aviso e atualiza com um clique.

Segurança: só `https`; a atualização é **bloqueada** se a release não trouxer o SHA-256 ou se o arquivo baixado não conferir.
Recomenda-se assinar o instalador com certificado de código (evita o aviso do SmartScreen e protege contra troca do arquivo).
Para testar sem internet: `VERTICE_UPDATE_URL` pode apontar para um JSON em `https://`.
