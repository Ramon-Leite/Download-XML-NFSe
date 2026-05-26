# ⏰ Guia: Como Configurar o Download em Segundo Plano no Windows

Este guia ensina como configurar o download automático de notas para rodar de forma **100% silenciosa (invisível)** uma ou mais vezes por dia, sem abrir telas ou atrapalhar quem estiver usando o computador.

---

## 🛠️ Passo a Passo para Configurar o Agendador de Tarefas do Windows

1. No teclado, pressione a tecla **Windows** e digite **Agendador de Tarefas** (ou *Task Scheduler*). Pressione Enter para abrir.
2. No menu do lado direito, clique em **Criar Tarefa Básica...** (ou *Create Basic Task*).
3. **Nome da Tarefa**: Digite um nome simples, como `Download NFSe Automatico`. Clique em **Avançar**.
4. **Disparador**: Escolha **Diariamente** (Daily) e clique em **Avançar**.
5. **Horário**: Defina a hora em que deseja que o download ocorra todos os dias (ex: às `13:45`). Clique em **Avançar**.
6. **Ação**: Escolha **Iniciar um programa** (Start a program) e clique em **Avançar**.
7. **Configuração do Programa**:
   * **Programa/script**: Digite `C:\Python314\pythonw.exe` (ou o caminho onde o Python do computador destino está instalado).
     * *Dica*: Usar o `pythonw.exe` (com o "w") garante que **nenhuma** janela preta de terminal apareça na tela do usuário.
   * **Adicione argumentos (opcional)**: Digite `sincronizar_direto.py`
   * **Iniciar em (opcional)**: Cole o caminho da pasta onde o projeto está localizado na máquina destino. Exemplo:
     `C:\Users\ramon\Documents\PROJETOS\Download XML NFSe`
8. Clique em **Avançar** e depois em **Concluir**.

---

## 🎉 Pronto!
O agendador agora está ativo. Todos os dias, no horário definido, o Windows irá disparar a varredura e download das notas em segundo plano de forma invisível. 

* **Como ver se funcionou?**
  Quando o operador abrir o sistema clicando no atalho **`Iniciar_Sistema.bat`**, todas as notas que foram baixadas automaticamente em segundo plano pelo agendador já estarão salvas no banco de dados e aparecerão de forma instantânea no painel!
