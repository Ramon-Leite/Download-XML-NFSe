# 📖 Guia de Instalação - NFS-e Nacional

Siga estes passos simples para colocar o programa para funcionar em um novo computador.

## 📋 Requisitos

- Python 3.11 ou 3.12 (Recomendado pela estabilidade)
- Certificado Digital A1 (.pfx) válido
- Conexão com internet

## 🔧 Instalação em um novo PC

1. **Copie a pasta**: Copie a pasta inteira `Download XML NFSe` para o novo computador.
2. **Instale o Python**: Baixe e instale o **Python 3.12** (marque "Add Python to PATH").

## 3. Instalar os Componentes
1. Entre na pasta `Download XML NFSe`.
2. No topo da janela da pasta (onde aparece o endereço), apague tudo, digite **`powershell`** e aperte Enter.
3. Na janela preta/azul que abrir, digite o comando abaixo e aperte Enter:
   ```powershell
   pip install -r requirements.txt
   ```
4. Espere terminar (vai aparecer um monte de letras, é normal).

## 4. Rodar o Programa (Como Janela)
Toda vez que quiser abrir o programa como uma janela independente (sem usar o navegador):
1. Dentro da pasta, abra o **powershell**.
2. Digite o comando:
   ```powershell
   python launcher.py
   ```
3. O programa abrirá em uma janela própria chamada "NFS-e Nacional".

> **Dica**: Você também pode rodar do jeito antigo se preferir (`streamlit run app.py`), mas o modo janela é melhor para o dia a dia do escritório.

---
**Dica**: Se quiser levar o que já foi feito (empresas cadastradas), peça para ele copiar as pastas `data` e `xmls` junto.
