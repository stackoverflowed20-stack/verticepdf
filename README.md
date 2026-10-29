<div align="center">

# Vértice PDF

**Editor de PDF para Windows: edite texto palavra por palavra, anote, assine, faça OCR e organize seus documentos em um só lugar.**

![Versão](https://img.shields.io/badge/vers%C3%A3o-1.10.0-1f4fe0)
![Python](https://img.shields.io/badge/python-3.12-3776ab)
![Qt](https://img.shields.io/badge/interface-PySide6-41cd52)
![Plataforma](https://img.shields.io/badge/plataforma-Windows%2010%2F11-0078d4)
![Licença](https://img.shields.io/badge/licen%C3%A7a-AGPL--3.0-blue)

</div>

---

## Sumário

- [Visão geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Instalação](#instalação)
- [Atualização automática](#atualização-automática)
- [Para desenvolvedores](#para-desenvolvedores)
- [Gerar o instalador](#gerar-o-instalador)
- [Publicar uma versão](#publicar-uma-versão)
- [Arquitetura](#arquitetura)
- [Testes](#testes)
- [Solução de problemas](#solução-de-problemas)
- [Limitações conhecidas](#limitações-conhecidas)
- [Licença](#licença)
- [Histórico de versões](#histórico-de-versões)

---

## Visão geral

O Vértice PDF é um editor de PDF desktop em **Python + PySide6 (Qt) + PyMuPDF**. O diferencial é a edição de texto
precisa: ao clicar em uma palavra, só ela é trocada, mantendo fonte, tamanho e cor do restante da linha.

O código é original. A interface segue o design "Central de documentos": página inicial com busca, recentes com
miniatura e ferramentas agrupadas, e um visualizador com abas de ferramentas (Visualizar, Editar, Converter,
Anotar, Página, Proteger). Há tema claro, escuro e seguir o sistema.

## Funcionalidades

| Área | O que faz |
|---|---|
| **Visualizar** | Várias abas, arrastar e soltar, PDFs com senha, recentes, busca (`Ctrl+F`), zoom (`Ctrl`+roda), miniaturas e marcadores (`F4`), seleção e cópia de texto entre páginas (`Ctrl+C`, `Ctrl+A`) |
| **Editar texto** | **Por palavra:** clique em uma palavra e troque só ela, com barra de fonte, tamanho, negrito, itálico e cor. **Por parágrafo:** reflow com a fonte original quando possível. Adicionar texto, realçar, apagar área, desfazer e refazer (até 40 passos) |
| **Localizar e substituir** | `Ctrl+H`, mantendo fonte, tamanho e cor |
| **Anotações** | Seta, linha, retângulo, elipse, caneta, nota, caixa de texto e carimbos (APROVADO, URGENTE, data…). Botão direito para editar ou excluir |
| **Assinatura** | Digital com certificado `.pfx`/`.p12` (visível ou invisível, várias assinaturas), verificação de integridade e emissor, criação de certificado de teste. Também assinatura desenhada ou por imagem |
| **Formulários** | Preenche campos AcroForm |
| **OCR** | Gera PDF pesquisável a partir de documentos digitalizados (Tesseract, português e inglês) |
| **Páginas** | Reordenar, girar, duplicar, excluir, recortar, extrair para novo PDF, inserir páginas de outro PDF |
| **Documento** | Marca d'água, cabeçalho, rodapé e numeração de páginas, limpeza de metadados |
| **Lote** | Combinar, dividir (por página, a cada N ou por intervalos), comprimir e converter (PNG, JPG, TXT) |
| **Comprimir** | Três níveis; nunca devolve um arquivo maior que o original |
| **Proteger** | Criptografia AES-256 com permissões e remoção de senha |
| **Criar e imprimir** | PDF em branco (A4, Carta…) ou a partir de imagens; impressão com intervalo de páginas |
| **Menu Arquivo** | Abrir (`Ctrl+O`), abrir recentes, criar PDF (`Ctrl+N`), salvar, salvar como, exportar, abrir local do arquivo, propriedades do documento (`Ctrl+D`, edita título, autor, assunto e palavras-chave), imprimir e preferências (aparência e atualização automática) |
| **Exportar** | **Word** (texto com tamanho, negrito, itálico e cor; imagens não são levadas), **Excel** (cada tabela detectada vira uma planilha; sem tabelas, o texto vai linha a linha), **PowerPoint** (um slide por página, como imagem) e **imagem** PNG/JPEG (uma por página) |
| **Compartilhar** | Copia o arquivo para colar em e-mail, chat ou pasta |
| **Segurança dos dados** | Recuperação automática a cada 45 s, janela única, aviso antes de editar PDF assinado |

## Instalação

### Para usuários

1. Abra a página de [**Releases**](https://github.com/stackoverflowed20-stack/verticepdf/releases/latest).
2. Em **Assets**, baixe `VerticePDF-Setup-x.y.z.exe`.
3. Execute o instalador. Se o Windows mostrar o aviso do SmartScreen, clique em **Mais informações → Executar assim mesmo**
   (o instalador ainda não tem assinatura de código).
4. Escolha o tipo de instalação:
   - **Completa (recomendada):** inclui o OCR.
   - **Compacta:** sem OCR, download menor.
5. Opcionalmente crie o atalho na área de trabalho e associe os arquivos `.pdf` ao Vértice PDF.

**Requisitos:** Windows 10 ou 11 de 64 bits. Não é preciso instalar Python nem outros programas.

Seus dados ficam em `%APPDATA%\VerticePDF` (configurações, log e cópias de recuperação) e **não** são apagados
ao atualizar.

## Atualização automática

Menu **≡ → Verificar atualizações…**. O programa também confere sozinho uma vez por dia e avisa na barra inferior.

Ao clicar em **Atualizar agora**, ele baixa o instalador novo, confere o SHA-256, pergunta se quer salvar o que está
aberto, fecha, instala **por cima** da versão atual (mesma pasta e mesmas opções) e reabre sozinho. Não é preciso
desinstalar.

Segurança: só aceita `https` e **bloqueia** a atualização se a release não trouxer o SHA-256 ou se o arquivo baixado
não conferir.

## Para desenvolvedores

### Executar a partir do código

```powershell
git clone https://github.com/stackoverflowed20-stack/verticepdf.git
cd verticepdf
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py              # ou: python main.py arquivo.pdf
```

Requer Python 3.10 ou superior, de 64 bits. O build oficial usa Python 3.12.

### OCR no modo desenvolvimento

Instale o [Tesseract (build UB Mannheim)](https://github.com/UB-Mannheim/tesseract/wiki) e marque o idioma
**Portuguese**. O programa procura primeiro o Tesseract embutido no instalador, depois o do `PATH` e por fim
`C:\Program Files\Tesseract-OCR`.

### Autoteste

```powershell
python main.py --selftest relatorio.txt
```

Verifica motor de PDF, edição, assinatura, OCR e criptografia. Termina com `RESULTADO: TUDO OK` quando está tudo certo.

## Gerar o instalador

Pré-requisitos no PC de build: Python 3.12 de 64 bits, internet (na primeira vez) e [Inno Setup 6](https://jrsoftware.org/isdl.php).
O 7-Zip é necessário para embutir o OCR; o build tenta instalar o Inno Setup e o 7-Zip sozinho com o `winget`.

```powershell
.\build_installer.bat            # completo, com OCR
.\build_installer.bat --no-ocr   # sem OCR (menor)
```

O script cria um ambiente virtual, gera o executável com PyInstaller, roda o autoteste no programa empacotado e compila
o instalador. Resultado:

```
installer\VerticePDF-Setup-<versão>.exe
installer\VerticePDF-Setup-<versão>.exe.sha256
```

| Etapa | O que acontece |
|---|---|
| 1/5 | Ícone e metadados da versão |
| 2/5 | Executável com PyInstaller (pasta `dist\VerticePDF`) |
| 3/5 | Autoteste do programa empacotado; se falhar, o instalador não é gerado |
| 4/5 | Componentes: Tesseract (OCR) e Visual C++ Runtime |
| 5/5 | Instalador com Inno Setup |

Se a etapa 4 mostrar `AVISO` ou `Instalador será gerado SEM o componente de OCR`, apague a pasta `redist` e rode de novo.

## Publicar uma versão

1. Em `version.py`, aumente `__version__` (por exemplo `1.9.1`) e confira o `UPDATE_URL`:
   ```python
   UPDATE_URL = "https://api.github.com/repos/stackoverflowed20-stack/verticepdf/releases/latest"
   ```
   Edite o arquivo com um editor de texto. O PowerShell pode gravá-lo com um caractere invisível (BOM).
2. Envie ao GitHub e crie a tag:
   ```powershell
   git add .
   git commit -m "Versao 1.9.1"
   git tag v1.9.1
   git push origin main --tags
   ```
3. O workflow **Gerar instalador (Windows)** roda os testes, compila, testa a instalação e a desinstalação e publica o
   instalador e o `.sha256` na release. Também é possível gerar o instalador no PC e anexá-lo manualmente em **Releases**.
4. O repositório precisa ser **público** e a release não pode ser rascunho nem pré-lançamento, senão o programa
   instalado não encontra a atualização.

Para testar sem alterar o código, defina a variável de ambiente `VERTICE_UPDATE_URL`.

## Arquitetura

```
VerticePDF/
├── main.py            Janela principal, página inicial, abas, menu, atualização, autoteste
├── viewer.py          Visualizador e faixa de ferramentas (PdfView), histórico, autosave
├── textedit.py        Edição por palavra e por parágrafo, substituição, escolha de fonte
├── annots.py          Anotações (setas, formas, notas, carimbos)
├── signing.py         Assinatura digital e verificação (pyHanko)
├── exporters.py       Exportação para Word, Excel, PowerPoint e imagens (sem dependências extras)
├── pagetools.py       Recortar, extrair, inserir páginas, marca d'água, cabeçalho e rodapé
├── ops.py             Operações em lote: combinar, dividir, comprimir, converter, OCR, criptografar
├── dialogs.py         Diálogos das ferramentas
├── ui_common.py       Tema (claro/escuro), QSS, widgets reutilizáveis
├── icons.py           Ícones vetoriais desenhados em código
├── recovery.py        Recuperação automática de documentos não salvos
├── updater.py         Verificação e instalação de atualizações
├── version.py         Nome, versão e endereço de atualização
├── build.py           Pipeline de build (PyInstaller, autoteste, Inno Setup)
├── installer.iss      Script do instalador
├── scripts/           Teste de instalação no Windows
├── tests/             Testes automatizados
└── .github/workflows/ Build do instalador no GitHub Actions
```

**Tecnologias:** PySide6 (interface), PyMuPDF (leitura, edição e renderização), pyHanko (assinatura digital),
Tesseract via pytesseract (OCR), PyInstaller (empacotamento) e Inno Setup (instalador).

**Dados do usuário:** `%APPDATA%\VerticePDF` contém `verticepdf.log` e a pasta `recovery`.

## Testes

```powershell
pip install pytest
python -m pytest -q
```

A suíte cobre o motor de PDF, a edição de palavras em PDFs reais (Chrome, LibreOffice, wkhtmltopdf e ReportLab, em
`tests/data`), ferramentas de página, recuperação, atualização e a página inicial. Em Linux, defina
`QT_QPA_PLATFORM=offscreen`.

O workflow do GitHub também roda `scripts/install_smoke.ps1`: instala em silêncio, executa o autoteste do programa
instalado, testa a janela única e desinstala.

## Solução de problemas

| Problema | O que fazer |
|---|---|
| O OCR avisa "Tesseract não encontrado" | O instalador foi gerado sem OCR. Reinstale a versão **Completa**, ou gere o instalador de novo (veja [Gerar o instalador](#gerar-o-instalador)) |
| "O endereço de atualização ainda não foi configurado" | O `UPDATE_URL` estava vazio quando o instalador foi gerado. Preencha em `version.py` e gere o instalador de novo |
| A verificação de atualização dá erro de conexão | O repositório está privado ou a release não foi publicada. Teste o endereço do `UPDATE_URL` no navegador |
| Erro inesperado | Veja o log em `%APPDATA%\VerticePDF\verticepdf.log` (caminho também em **≡ → Sobre**) |
| Build falha com `invalid non-printable character U+FEFF` | O `version.py` foi gravado com BOM. Salve-o como UTF-8 no Bloco de Notas |
| Aviso do SmartScreen ao instalar | Esperado sem assinatura de código. Clique em **Mais informações → Executar assim mesmo** |

## Limitações conhecidas

- **Edição por parágrafo** aplica um único estilo ao parágrafo inteiro.
- **Edição por palavra** não funciona em páginas giradas nem em texto vertical. A fonte original só é reaproveitada se
  estiver embutida com todos os glifos necessários ou instalada no Windows; senão usa Helvetica, Times ou Courier e o
  programa avisa. O fundo é amostrado da página, então funciona melhor em fundos lisos. Se o texto novo não couber, a
  edição é desfeita com um aviso.
- **Assinatura digital:** a validade jurídica depende do certificado. Certificados autoassinados garantem a integridade,
  mas aparecem como "emissor não verificado". Certificados ICP-Brasil A1 (`.pfx`) funcionam. Tokens e cartões A3
  (PKCS#11), carimbo de tempo (TSA) e verificação de revogação (LTV) ainda não são suportados. Editar e salvar um PDF
  assinado invalida a assinatura (o programa avisa antes).
- **PDFs digitalizados** não têm texto selecionável nem editável. Rode o OCR primeiro.
- Texto adicionado em páginas giradas pode ficar fora de posição.
- O instalador não tem assinatura de código, o que gera o aviso do SmartScreen.

## Licença

O Vértice PDF usa o **PyMuPDF/MuPDF**, licenciado sob **AGPL-3.0** (ou licença comercial da Artifex). Por isso:

- Para uso pessoal ou interno, não há restrição adicional.
- Ao **distribuir** o programa, é preciso oferecer o código-fonte a quem o recebe e manter a mesma licença
  (AGPL-3.0). Manter este repositório público atende a isso. Adicione um arquivo `LICENSE` com o texto da AGPL-3.0.
- Para distribuir sem abrir o código, é necessário adquirir a licença comercial da Artifex ou trocar o PyMuPDF por
  `pypdfium2` + `pypdf`, com menos recursos de edição.

Os componentes de terceiros e suas licenças estão em [`THIRD_PARTY_NOTICES.txt`](THIRD_PARTY_NOTICES.txt):
PySide6 (LGPL-3.0), pyHanko (MIT), cryptography (Apache-2.0/BSD), Pillow (HPND), pytesseract e Tesseract (Apache-2.0).

## Histórico de versões

| Versão | Destaques |
|---|---|
| **1.10.0** | Menu **Arquivo** (abrir, recentes, criar, salvar, exportar para Word/Excel/PowerPoint/imagem, local do arquivo, propriedades, imprimir, preferências) e barra de título única: minimizar, maximizar e fechar na linha das abas |
| **1.9.2** | A barra da ferramenta ativa some quando não há opções a ajustar (a dica passa para a barra de status), liberando mais espaço para a página |
| **1.9.1** | Topo do visualizador mais compacto (abas, barra, faixa de ferramentas e barra de propriedades), com cerca de 45 px a mais para a página |
| **1.9.0** | Visual "Central de documentos": sidebar branca, busca com `Ctrl+K`, zona de abrir PDF, recentes com miniatura, filtros de ferramentas, cartão Compartilhar PDF, abas de 44 px |
| **1.8.0** | Atualização pelo próprio programa, sem desinstalar, com verificação SHA-256 |
| **1.7.0** | Edição por palavra validada em PDFs reais, recuperação automática, janela única, refazer, localizar e substituir, marca d'água, cabeçalho e rodapé, recortar, extrair, tema claro/escuro |
| **1.6.0** | Faixa de ferramentas com abas Visualizar, Editar, Converter, Anotar, Página e Proteger |
| **1.5.x** | Pacote menor e abertura mais rápida; OCR como componente opcional do instalador |
| **1.3** | Nova interface: tela inicial com recentes, barra lateral e barra de propriedades contextual |
