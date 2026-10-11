"""RunPod: создать под, узнать SSH, проверить баланс, удалить. GraphQL API, ключ из .env.

Опыт (2026-10-04):
  - только SECURE cloud: на community попались под с неработающей CUDA
    ("CUDA unknown error") и под без публичного IP (SSH невозможен);
  - SSH-ключ ~/.ssh/runpod_ed25519 передаётся поду через env PUBLIC_KEY —
    в настройках RunPod ничего добавлять не нужно;
  - на образе runpod/pytorch нет rsync — копировать scp;
  - предоплаченный баланс — жёсткий лимит денег; лимит времени — `timeout`
    вокруг команды на поде плюс проверка баланса;
  - после create проверить CUDA: python -c "import torch; print(torch.cuda.is_available())".
    False — под неисправен, удалить и создать новый.

Команды:
    python3 templates/runpod.py balance
    python3 templates/runpod.py gpus                       доступность и цены
    python3 templates/runpod.py create --gpu "NVIDIA GeForce RTX 4090" --name emb
    python3 templates/runpod.py ssh <pod_id>               печатает ssh/scp команды
    python3 templates/runpod.py list
    python3 templates/runpod.py terminate <pod_id>

Под удаляется автоматически сразу после скачивания результатов и сверки хешей
(notes/workflow.md §6), неисправный — сразу; не оставлять работать вхолостую.
"""
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_FILE = os.path.expanduser("~/.ssh/runpod_ed25519")
IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"


def api_key():
    for line in open(os.path.join(ROOT, ".env")):
        if line.startswith("RUNPOD_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("ОТКАЗ: RUNPOD_API_KEY нет в .env")


def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.runpod.io/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        # User-Agent обязателен: со стандартным Python-urllib API отвечает 403
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key()}",
                 "User-Agent": "stand-runpod/1"})
    d = json.load(urllib.request.urlopen(req))
    if d.get("errors"):
        sys.exit(f"ОТКАЗ RunPod: {d['errors'][0]['message']}")
    return d["data"]


def ssh_port(pod_id):
    d = gql("query($id:String!){pod(input:{podId:$id}){runtime{ports{ip isIpPublic privatePort publicPort}}}}",
            {"id": pod_id})["pod"]
    ports = ((d or {}).get("runtime") or {}).get("ports") or []
    return next(((p["ip"], p["publicPort"]) for p in ports if p["privatePort"] == 22 and p["isIpPublic"]), None)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "balance":
        print(gql("query{myself{clientBalance}}")["myself"]["clientBalance"])
    elif cmd == "gpus":
        for g in gql("query{gpuTypes{id memoryInGb securePrice lowestPrice(input:{gpuCount:1}){stockStatus}}}")["gpuTypes"]:
            if g.get("securePrice"):
                print(f"{g['id']:40} {g['memoryInGb']:3} ГБ  secure ${g['securePrice']}/ч  "
                      f"{(g.get('lowestPrice') or {}).get('stockStatus')}")
    elif cmd == "create":
        args = dict(zip(sys.argv[2::2], sys.argv[3::2]))
        if not os.path.exists(KEY_FILE):
            sys.exit(f"ОТКАЗ: нет {KEY_FILE}; создать: ssh-keygen -t ed25519 -N '' -f {KEY_FILE}")
        inp = {"name": args.get("--name", "stand"), "cloudType": "SECURE", "gpuCount": 1,
               "gpuTypeId": args["--gpu"], "imageName": args.get("--image", IMAGE),
               "containerDiskInGb": int(args.get("--disk", 30)), "volumeInGb": 0,
               "ports": "22/tcp", "startSsh": True, "supportPublicIp": True,
               "env": [{"key": "PUBLIC_KEY", "value": open(KEY_FILE + ".pub").read().strip()}]}
        d = gql("mutation($in:PodFindAndDeployOnDemandInput){podFindAndDeployOnDemand(input:$in){id costPerHr}}",
                {"in": inp})["podFindAndDeployOnDemand"]
        print(f"под {d['id']}, ${d['costPerHr']}/ч; жду SSH…", flush=True)
        for _ in range(60):
            ep = ssh_port(d["id"])
            if ep:
                print(f"ssh -i {KEY_FILE} -p {ep[1]} root@{ep[0]}")
                return
            time.sleep(10)
        sys.exit(f"ОТКАЗ: SSH не появился за 10 мин; удалить: terminate {d['id']}")
    elif cmd == "ssh":
        ep = ssh_port(sys.argv[2])
        if not ep:
            sys.exit("нет публичного SSH")
        print(f"ssh -i {KEY_FILE} -p {ep[1]} root@{ep[0]}")
        print(f"scp -i {KEY_FILE} -P {ep[1]} <файлы> root@{ep[0]}:/root/")
    elif cmd == "list":
        for p in gql("query{myself{pods{id name desiredStatus costPerHr}}}")["myself"]["pods"]:
            print(p)
    elif cmd == "terminate":
        gql("mutation($id:String!){podTerminate(input:{podId:$id})}", {"id": sys.argv[2]})
        print("удалён", sys.argv[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
