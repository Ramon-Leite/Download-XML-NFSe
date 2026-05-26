# 📄 Fiscal Manager - NFS-e Portal Nacional

O **Fiscal Manager** é uma aplicação corporativa de altíssimo nível desenvolvida para automatizar a busca, download, gerenciamento e apuração de Notas Fiscais de Serviço Eletrônicas (NFS-e) do padrão Nacional da Receita Federal. 

Substituindo a antiga arquitetura pesada em Streamlit, o sistema opera sob um backend assíncrono robusto em **FastAPI** e uma interface de página única (**SPA**) baseada no design moderno e fluído **Material Design 3 (M3) + Tailwind CSS**, otimizada para máximo desempenho e com suporte a tema escuro profundo (OLED).

---

## 💎 Diferenciais e Recursos Premium

- ⚡ **SPA de Alta Performance**: Troca instantânea de telas sem recarregamento de página.
- 🏢 **Multi-Empresa**: Cadastro ilimitado de contribuintes com upload e validação de certificados digitais A1 (.pfx).
- 🕒 **Varredura Oculta em Segundo Plano**: Inicialização desvinculada que mantém o agendador e o banco de dados rodando em segundo plano de forma 100% silenciosa após o fechamento do console.
- 📊 **Estatísticas e Bento Analytics**: Gráfico de faturamento anual por competência e rankings de empresas em tempo real (utilizando Chart.js).
- 📁 **Destino de XMLs Customizável**: Escolha diretamente no painel de configurações a pasta do computador (ou rede/pendrive) onde deseja salvar organizadamente os XMLs baixados.
- 🛡️ **Alertas Inteligentes de Certificado**: Toasts automáticos de aviso/erro no boot do sistema caso o certificado A1 esteja próximo de vencer ou já expirado.
- 🚀 **Auto-Updater 1-Clique**: Verifique atualizações na nuvem do seu GitHub e atualize o sistema de forma 100% autônoma pelo painel web, preservando integralmente suas configurações locais, chaves e banco de dados.

---

## 📂 Estrutura Organizada do Projeto

```
Download XML NFSe/
├── app.py                      # Servidor FastAPI principal (Backend e SPA host)
├── launcher.py                 # Inicializador invisível (Win32 Detach)
├── sincronizar_direto.py       # Script avulso para agendamento invisível
├── updater.py                  # Script desacoplado de auto-atualização
├── config.py                   # Configurações do sistema e do atualizador
├── requirements.txt            # Dependências leves do Python
├── fiscal.ico                  # Ícone de alta resolução do Windows
├── Instalar_Fiscal_Manager.bat # Script gerador do atalho na Área de Trabalho
├── Iniciar_Sistema.bat         # Script atalho do operador
├── Sincronizar_Segundo_Plano.bat # Script de sincronização silenciosa
├── api/                        # Conector seguro da API do DFe Nacional
├── database/                   # Modelos e repositórios SQLite locais
├── services/                   # Motores de Download, PDF e Agendador
└── static/                     # Interface SPA estática (HTML, CSS e JS)
```

---

## 🔧 Como Rodar no Computador

### 1. Criar Atalho na Área de Trabalho com Ícone
Dê dois cliques no arquivo **`Instalar_Fiscal_Manager.bat`**. O instalador executará o comando PowerShell nativo e criará o ícone **Fiscal Manager** na sua Área de Trabalho com logotipo personalizado!

### 2. Inicialização Comum
* Dê dois cliques no atalho **Fiscal Manager** da Área de Trabalho ou execute o arquivo **`Iniciar_Sistema.bat`**.
* O backend FastAPI subirá em segundo plano de forma invisível na porta `8000`.
* A interface do aplicativo abrirá instantaneamente em **Modo App** no seu navegador padrão, ocultando a barra de endereços para parecer um aplicativo nativo do computador.

### 3. Execução Silenciosa para Computador de Agendamento (24/7)
Se você for deixar o sistema rodando em um computador dedicado apenas para executar o agendamento de downloads automáticos, consulte o guia passo a passo em **`Como_Configurar_Agendamento.md`** para registrar a sincronização silenciosa no **Agendador de Tarefas do Windows** sem exibir nenhuma janela de terminal ou navegador na tela de quem trabalha no computador!

---

## 🚀 Como Atualizar no Futuro (Atualizador 1-Clique)

Para lançar atualizações para o computador do seu cliente através do seu repositório no GitHub:

1. Modifique os códigos no seu repositório do GitHub.
2. Compacte os arquivos modificados em um arquivo chamado **`update.zip`** (⚠️ **NÃO** inclua a pasta `data/` nem a pasta `xmls/` para não sobrescrever os dados do usuário).
3. Crie uma **Release** no seu GitHub (ex: tag `v1.1`) e anexe o `update.zip`.
4. Atualize o arquivo **`versao_atual.json`** na raiz da branch `main` com as notas de versão e o link de download do zip da release.
5. O operador só precisará acessar a aba de Configurações no sistema, clicar em **Procurar Atualizações** e depois em **Atualizar e Reiniciar Agora**!

---

**Versão**: 1.0 (Estável)  
**Desenvolvedor**: Ramon Leite  
**Tecnologias**: Python 3.14, FastAPI, Material Design 3, Tailwind CSS, SQLite, APScheduler.
