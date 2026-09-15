import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

export function activate(context: vscode.ExtensionContext) {
    console.log('Congratulations, your extension "ai-chat-logger" is now active!');

    // Hello World 명령어 (기존)
    const helloDisposable = vscode.commands.registerCommand('ai-chat-logger.helloWorld', () => {
        vscode.window.showInformationMessage('Hello World from Ai_chat_logger!');
    });
    context.subscriptions.push(helloDisposable);

    // 대화 저장 명령어 (추가)
    const saveChatDisposable = vscode.commands.registerCommand('ai-chat-logger.saveChat', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showErrorMessage('No active editor!');
            return;
        }

        const text = editor.document.getText();
        const rawDir = '/Users/project/agora/apps/chronicle/data/raw/';
        if (!fs.existsSync(rawDir)) {
            fs.mkdirSync(rawDir, { recursive: true });
        }

        const date = new Date();
        const dateStr = `${date.getFullYear()}-${(date.getMonth()+1).toString().padStart(2,'0')}-${date.getDate().toString().padStart(2,'0')}`;
        let part = 1;
        let filePath = path.join(rawDir, `chat_${dateStr}_part${part}.jsonl`);
        let fileSize = fs.existsSync(filePath) ? fs.statSync(filePath).size : 0;

        const lines = text.split('\n').filter(line => line.trim() !== '');
        for (const line of lines) {
            const obj = {
                year: date.getFullYear(),
                month: date.getMonth() + 1,
                step: 1,
                title: "unknown",
                user: line,
                assistant: "",
                reason: ""
            };
            const jsonl = JSON.stringify(obj) + '\n';

            if (fileSize + Buffer.byteLength(jsonl) > 20 * 1024 * 1024) {
                part += 1;
                filePath = path.join(rawDir, `chat_${dateStr}_part${part}.jsonl`);
                fileSize = 0;
            }
            fs.appendFileSync(filePath, jsonl, { encoding: 'utf8' });
            fileSize += Buffer.byteLength(jsonl);
        }
        vscode.window.showInformationMessage('AI 대화 로그 저장 완료!');
    });
    context.subscriptions.push(saveChatDisposable);
}

export function deactivate(): void {}