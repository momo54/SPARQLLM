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
            const pythonScriptPath = path.join(extensionPath, 'SPARQLLM/', 'query_request.py');

            // Détection de l'environnement virtuel
            const workspaceFolder = vscode.workspace.workspaceFolders?.[0].uri.fsPath;
            const pythonPath = path.join(workspaceFolder || '', '.venv', 'bin', 'python'); // Ajuster pour Windows: '.venv\\Scripts\\python.exe'

            // Exécution du script Python
            exec(`"${pythonPath}" "${pythonScriptPath}" "${filePath}"`, (error, stdout, stderr) => {
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
