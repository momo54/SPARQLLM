import * as path from 'path';
import * as vscode from 'vscode';
import { exec } from 'child_process';

export function activate(context: vscode.ExtensionContext) {
    const runPythonScript = vscode.commands.registerCommand('extension.runSparqllm', () => {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            const filePath = editor.document.uri.fsPath;
    
            // Récupérer le chemin absolu vers le répertoire de l'extension
            const extensionPath = context.extensionPath;
            const pythonScriptPath = path.join(extensionPath, 'SPARQLLM', 'query_request.py');
            
            // Spécifier le chemin complet vers l'exécutable Python dans l'environnement virtuel embarqué (Windows)
            const venvPath = path.join(extensionPath, '.env', 'Scripts', 'python.exe'); // Environnement virtuel dans .env
            
            exec(`"${venvPath}" "${pythonScriptPath}" "${filePath}"`, (error, stdout, stderr) => {
                if (error) {
                    vscode.window.showErrorMessage(`Erreur: ${stderr}`);
                    return;
                }
                vscode.window.showInformationMessage(`Sortie: ${stdout}`);
            });
        } else {
            vscode.window.showErrorMessage("Aucun fichier ouvert dans l'éditeur.");
        }
    });
       
    

    context.subscriptions.push(runPythonScript);
}

export function deactivate() {}
