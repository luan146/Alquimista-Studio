# Índice do manifesto

O ALQuimista mantém `manifesto_alquimista.json` como fonte portátil e legível.
Após uma gravação bem-sucedida, também é criado o índice secundário
`indice_manifesto_alquimista.sqlite3`.

O índice usa SQLite da biblioteca padrão do Python, com consultas por:

- chave estável do documento;
- fonte e contêiner;
- data de atualização.

Ele é reconstruído em arquivo temporário e substituído atomicamente. Se a
reconstrução falhar, o manifesto JSON continua válido e a falha é registrada;
o índice pode ser recriado na próxima execução.
