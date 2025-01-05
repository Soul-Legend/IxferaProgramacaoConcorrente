from random import randint, seed
from sys import argv
from threading import Condition, Lock, Semaphore, Thread
from time import perf_counter, sleep

from fila import Fila

# Semáforos binários para sincronização das saídas impressas no terminal.
sinc_fila_sem = Semaphore(0)
sinc_ixfera_sem = Semaphore(0)

# Semáforo usado para prevenir que o número de pessoas na Ixfera ultrapasse o número de vagas.
ocupacao_sem = None

# Trava geral que protege o contador e a fila.
ixfera_trava = Lock()

# Verifica a condição de pausa da experiência. É notificada quando uma pessoa
# entra em uma fila vazia ou quando a Ixfera fica vazia.
pausa_cond = Condition(ixfera_trava)

# Semáforos e threads de cada pessoa.
pessoas_sem = []
threads_pessoas = []

# Fila de pessoas que estão esperando o ingresso na atração.
fila_pessoas = Fila()

# Contador de pessoas que estão dentro da atração em um determinado momento.
cont_pessoas_ixfera = 0


def pessoa_worker(ident, faixa_etaria, tempo_perm, out_tempos_espera):
    global cont_pessoas_ixfera

    tempo_anterior_espera = perf_counter()

    pessoa = f"[Pessoa {ident + 1} / {faixa_etaria}]"

    with ixfera_trava:
        print(f"{pessoa} Aguardando na fila.", flush=True)

        fila_pessoas.put(ident)

        # A fila não está mais vazia.
        if fila_pessoas.qsize() == 1:
            pausa_cond.notify()

    # Notifica o criador que a pessoa terminou de entrar na fila.
    sinc_fila_sem.release()

    # Espera a autorização do ingresso na atração.
    pessoas_sem[ident].acquire()

    with ixfera_trava:
        cont_pessoas_ixfera += 1

        print(
            f"{pessoa} Entrou na Ixfera (quantidade = {cont_pessoas_ixfera}).",
            flush=True,
        )

    out_tempos_espera[ident] = perf_counter() - tempo_anterior_espera

    # Notifica a thread principal que a pessoa terminou de ingressar na atração.
    sinc_ixfera_sem.release()

    sleep(tempo_perm / 1000)

    with ixfera_trava:
        cont_pessoas_ixfera -= 1

        print(
            f"{pessoa} Saiu da Ixfera (quantidade = {cont_pessoas_ixfera}).",
            flush=True,
        )

        # Ixfera ficou vazia.
        if cont_pessoas_ixfera == 0:
            pausa_cond.notify()

    # Libera uma vaga na Ixfera.
    ocupacao_sem.release()


def criador_worker(
    num_pessoas, faixas_etarias, tempo_perm, tempo_max_inter, out_tempos_espera
):
    for ident in range(num_pessoas):
        thread_pessoa = Thread(
            target=pessoa_worker,
            name=f"Pessoa {ident}",
            args=(ident, faixas_etarias[ident], tempo_perm, out_tempos_espera),
        )
        threads_pessoas.append(thread_pessoa)

        try:
            thread_pessoa.start()
        except RuntimeError as err:
            # Exceção causada ao não haver mais memória para criar novas threads.
            print("\n     ************\nErro ao iniciar thread\n     ************")
            print(f"Mensagem de erro: {str(err)}")

            import os

            # Sai do programa.
            os._exit(-1)

        # Caso não haja mais pessoas que entrarão na fila, não fará sentido esperar esse tempo.
        if ident < num_pessoas - 1:
            sleep(randint(0, tempo_max_inter) / 1000)

        # Aguarda a thread pessoa ingressar na fila (imprimir mensagem).
        sinc_fila_sem.acquire()


def obter_args():
    if len(argv) < 7:
        raise RuntimeError("Insira os argumentos corretos.")

    args = list(map(int, argv[1:]))

    (num_pessoas, num_vagas, permanencia, max_intervalo, semente, unid_tempo) = args

    msgs = [
        "Número de pessoas",
        "Número de vagas",
        "Tempo de permanência",
        "Intervalo máximo",
        "Unidade de tempo",
    ]
    for msg, val in zip(
        msgs, [num_pessoas, num_vagas, permanencia, max_intervalo, unid_tempo]
    ):
        if val <= 0:
            raise RuntimeError(f"{msg} deve ser maior que zero.")

    if semente < 0:
        raise RuntimeError("Semente deve ser maior ou igual à zero.")

    # Limita o número de vagas com o número de pessoas.
    num_vagas = min(num_vagas, num_pessoas)

    return (num_pessoas, num_vagas, permanencia, max_intervalo, semente, unid_tempo)


def main():
    global ocupacao_sem
    global pessoas_sem

    (
        num_pessoas,
        num_vagas,
        permanencia,
        max_intervalo,
        semente,
        unid_tempo,
    ) = obter_args()

    tempo_perm = permanencia * unid_tempo
    tempo_max_inter = max_intervalo * unid_tempo

    seed(semente)

    ocupacao_sem = Semaphore(num_vagas)
    pessoas_sem = [Semaphore(0) for _ in range(num_pessoas)]

    tempo_anterior_simul = perf_counter()

    print("[Ixfera] Simulacao iniciada.")

    # Define randomicamente a faixa etária de todos os visitantes.
    faixas_etarias = [["A", "B", "C"][randint(0, 2)] for _ in range(num_pessoas)]

    # Registrará o tempo de espera de cada visitante na fila para a Ixfera.
    tempos_espera = [0] * num_pessoas

    criador_thread = Thread(
        target=criador_worker,
        name="Criador",
        args=(num_pessoas, faixas_etarias, tempo_perm, tempo_max_inter, tempos_espera),
    )
    criador_thread.start()

    # Quantidade de tempo em que a Ixfera está em funcionamento.
    tempo_ixfera = 0

    qtd_pessoas_atendidas = 0
    while qtd_pessoas_atendidas < num_pessoas:
        # Bloqueia até alguém chegar na fila.
        exp_atual = faixas_etarias[fila_pessoas.front(block=True)]

        tempo_anterior_ixfera = perf_counter()

        print(f"[Ixfera] Iniciando a experiencia {exp_atual}.", flush=True)

        # Fila de pessoas que assistiram à experiência.
        fila_experiencia = Fila()

        while qtd_pessoas_atendidas <= num_pessoas:
            with ixfera_trava:
                # Fila está vazia, mas ainda há pessoas na Ixfera.
                while fila_pessoas.empty() and cont_pessoas_ixfera != 0:
                    # Ficará esperando até que uma das condições acima seja falsa.
                    pausa_cond.wait()

                # A fila ainda está vazia e agora não há mais ninguém na Ixfera: condição de pausa.
                if fila_pessoas.empty() and cont_pessoas_ixfera == 0:
                    print(f"[Ixfera] Pausando a experiencia {exp_atual}.", flush=True)
                    break

            pessoa = fila_pessoas.front(block=False)

            # A primeira pessoa da fila é de uma faixa etária diferente.
            if faixas_etarias[pessoa] != exp_atual:
                break

            fila_pessoas.pop(block=False)

            # Se a atração está cheia, espera alguém sair.
            ocupacao_sem.acquire()

            fila_experiencia.put(pessoa)
            qtd_pessoas_atendidas += 1

            pessoas_sem[pessoa].release()

            sinc_ixfera_sem.acquire()

        # Garante que todas as pessoas que assistiram à experiência já saíram.
        while not fila_experiencia.empty():
            pessoa = fila_experiencia.get(block=False)
            threads_pessoas[pessoa].join()

        tempo_ixfera += perf_counter() - tempo_anterior_ixfera

    criador_thread.join()

    print("[Ixfera] Simulacao finalizada.")

    tempo_simul = perf_counter() - tempo_anterior_simul

    tempos_espera_faixas = {"A": 0, "B": 0, "C": 0}
    for pessoa, tempo in enumerate(tempos_espera):
        tempos_espera_faixas[faixas_etarias[pessoa]] += 1000 * tempo

    print("\nTempo medio de espera:")

    for faixa_etaria in ["A", "B", "C"]:
        qtd_pessoas_faixa = faixas_etarias.count(faixa_etaria)

        if qtd_pessoas_faixa != 0:
            media_faixa = tempos_espera_faixas[faixa_etaria] / qtd_pessoas_faixa
        else:
            media_faixa = 0

        print(f"Faixa {faixa_etaria}: {media_faixa:.2f}")

    taxa_ocupacao = tempo_ixfera / tempo_simul

    print(f"\nTaxa de ocupacao: {taxa_ocupacao:.2f}")


if __name__ == "__main__":
    main()
