# Ghi chú phân tích · Day 04

Họ và tên: Phạm Trung Kiên  
MSSV: 2A202603479

## 1. Case được chọn

- ID case: **E5 — Copilot Mission Control**.
- Câu hỏi: “Tìm incident gần đây về Copilot Mission Control trên GitHub. Nếu trường
components rỗng, có thể kết luận không có dịch vụ bị ảnh hưởng không?”
- Điểm ở lần chạy 1: **100/100**; điểm toàn bộ 22 case là **93.45/100** trong
`eval_before.json`. Đây là file baseline có sẵn đã được kiểm tra ở CP4.
- Lỗi được chọn: agent đã đọc thành công chi tiết incident nhưng chỉ dẫn trang
status chung, không đưa URL incident đã quan sát vào câu trả lời.
- Câu trả lời của agent (trích nguyên văn các đoạn liên quan từ baseline):

> Đã tìm thấy một incident gần đây liên quan đến dịch vụ Copilot Mission Control trên GitHub với ID "tc28c0wzrnpz".

> Nguồn dữ liệu: https://www.githubstatus.com, captured_at: 2026-11-09T03:50:47 (snapshot trạng thái)

Agent vẫn giải thích đúng rằng `components` rỗng không chứng minh không có ảnh hưởng.
Chọn lỗi nguồn này vì có bằng chứng trực tiếp trong trace và có thể kiểm tra bằng code,
dù judge đã chấm 100. Điểm cao không chứng minh đáp ứng đầy đủ contract nguồn.

## 2. Bằng chứng trong trace

Nguồn bằng chứng: phần tử `cases` có `id == "E5"` trong `eval_before.json`.
Agent gọi `get_status` ở step 1 và `get_incident_details` ở step 2.
Đây là phần trích từ tool event ở step 2; `result` chỉ giữ các trường liên quan:

```json
{
  "event": "tool",
  "step": 2,
  "name": "get_incident_details",
  "arguments": {
    "provider": "github",
    "incident_id": "tc28c0wzrnpz"
  },
  "result": {
    "ok": true,
    "id": "tc28c0wzrnpz",
    "url": "https://stspg.io/hj74883wgn0t",
    "captured_at": "2026-11-09T03:50:47.065020+00:00"
  }
}
```

URL `https://stspg.io/hj74883wgn0t` không xuất hiện trong `result.answer` của E5.
URL này có trong tool result, nên lỗi không do thiếu dữ liệu nguồn.

**Phân loại nguyên nhân:** model bỏ sót nguồn cụ thể khi tạo answer; điểm yếu cần sửa
nằm ở **loop**, vì loop cũ chấp nhận ngay `finish == 'stop'` và không có tool calls,
không kiểm tra điều kiện có nguồn. System prompt đã có câu “Dẫn nguồn từ tool”,
nhưng chỉ nhắc trong prompt không đảm bảo model luôn thực hiện.

Giới hạn 50 incident gần nhất và nội dung update có thể bị cắt vẫn tồn tại trong
tools; chúng không giải thích việc thiếu URL ở case E5 vì URL đã được trả đầy đủ.

## 3. Thay đổi đã thực hiện

- Sửa `run_agent` trong `agent.py`, thêm kiểm tra URL trước khi chấp nhận final answer.
- Sau mỗi `get_incident_details` có `ok: true`, lưu URL không rỗng vào tập
`incident_urls`; lấy trực tiếp từ kết quả tool, không hard-code ID hay URL E5.
- Khi model trả `finish == 'stop'` và không còn calls, nếu đã có URL incident thành
công nhưng answer không chứa URL nào trong tập, ghi event `validation_missing_source`
cùng step và `observed_urls` vào trace.
- Giữ nguyên assistant message vừa trả, thêm yêu cầu sửa có danh sách URL quan sát
được vào hội thoại rồi tiếp tục vòng lặp. Yêu cầu sửa là bổ sung ít nhất một URL
phù hợp đã đọc, không tự tạo URL hoặc suy diễn thêm thông tin.
- Mỗi lần sửa vẫn là một model call trong `max_steps`. Hết budget khi answer vẫn
thiếu nguồn thì trả `max_steps`, không trả `completed` và không chấp nhận answer
chưa qua kiểm tra.
- Không bắt nguồn khi chưa có incident thành công; URL trong kết quả tool thất bại
không được đưa vào tập bằng chứng.

**Vì sao chọn thay đổi này:** thêm điều kiện hoàn thành có thể kiểm tra bằng code,
thay vì chỉ trông chờ model làm đúng lời nhắc. Điều kiện này bắt được lỗi E5 ở
baseline và đáp ứng contract trong `tests/test_validation.py`.

**Kiểm chứng offline:**

```powershell
python -m unittest discover -s tests -v
```

Kết quả sau thay đổi: **53 tests, OK**, không còn test lỗi. Hai test kiểm tra nguồn
chưa đạt trước CP5 hiện đã đạt. Bổ sung 4 tests trong `tests/test_validation.py`:

- E5: link trang status chung chưa đủ; loop yêu cầu sửa để thêm URL incident thực.
- URL chưa quan sát được không đủ để vượt qua kiểm tra nguồn.
- Thiếu nguồn lặp lại không được vượt quá `max_steps`; trace và usage vẫn được giữ.
- URL trong tool result thất bại không tạo yêu cầu dẫn nguồn giả.

Đây là tests dùng fake provider và tool snapshot thật, không phải một lượt eval
bằng model thật sau cải tiến. Tại lúc hoàn thành CP5 chưa có điểm eval lần 2;
kết quả CP6 được ghi ở mục 4 bên dưới. `eval_before.json` được giữ nguyên.

**Giới hạn của thay đổi:** chỉ kiểm tra sự hiện diện của ít nhất một URL incident
đã quan sát trong answer, chưa kiểm tra ý nghĩa từng claim, nguồn cho mọi incident
hoặc mọi provider, và chưa ngăn URL đúng đi kèm kết luận sai. Chưa giải quyết các
lỗi khác như H1 không theo incident liên kết, H2 thiếu status hay H7 đoán trạng thái
sau timeout. Lượt sửa có thể tăng token và số model calls.

## 4. So sánh hai lần chạy

Đã đối chiếu `eval_before.json` và `eval_after.json` hiện có trong workspace.
Cả hai đều chứa đúng 22 case E1–E6, A1–A8, H1–H8, đều được chấm đầy đủ;
`score_0_100` khác `null`, không có case `unscored`.
Đã tính lại summary, điểm theo dimensions và score cap, đồng thời đối chiếu
`grade.mechanical` với trace bằng hàm kiểm tra của bộ eval.

Hai khối `config` **giống nhau hoàn toàn**:

```json
{
  "provider": "openrouter",
  "model": "openai/gpt-4.1-mini",
  "judge_provider": "openrouter",
  "judge_model": "openai/gpt-4.1-mini",
  "max_steps": 8,
  "dataset": "core"
}
```

Hai báo cáo cũng có cùng question, expected và scenario cho mỗi case. Timestamp
snapshot trong tool results đều là `2026-11-09T03:50:47.065020+00:00` cho GitHub
và `2026-11-09T03:50:47.638054+00:00` cho Cloudflare.

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Đã chấm / tổng số case | 22/22 | 22/22 |
| Điểm tổng | 93.45/100 | 94.95/100 |
| Điểm case đã chọn E5 | 100 | 94 |
| Model calls của agent | 53 | 56 |
| Model calls của judge | 22 | 22 |
| Tổng model calls | 75 | 78 |
| Tool calls | 40 | 44 |
| Token agent | 43.679 | 48.335 |
| Token judge | 36.151 | 37.929 |
| Tổng token | 79.830 | 86.264 |
| Chi phí agent (`usage.cost`) | 0.0248852 | 0.0271628 |
| Chi phí judge (`judge_usage.cost`) | 0.0187948 | 0.0197064 |
| Chi phí tổng do provider báo | 0.0436800 | 0.0468692 |
| Case có incident thành công nhưng answer thiếu mọi URL incident đã đọc | 2 (E5, H7) | 0 |
| Event `validation_missing_source` | 0 | 1 (A7, step 3) |

Điểm tổng tăng **1.50 điểm**; agent tăng 3 model calls; tổng token tăng 6.434;
tổng trường chi phí tăng 0.0031892. Các số chi phí được cộng từ usage trong hai
báo cáo đầy đủ, không suy ra từ bảng giá hay từ số dư tài khoản.

### Điểm từng case

| Case | Trước | Sau | Chênh lệch |
|---|---:|---:|---:|
| E1 | 100 | 100 | 0 |
| E2 | 100 | 100 | 0 |
| E3 | 100 | 100 | 0 |
| E4 | 100 | 100 | 0 |
| E5 | 100 | 94 | -6 |
| E6 | 100 | 100 | 0 |
| A1 | 100 | 100 | 0 |
| A2 | 100 | 100 | 0 |
| A3 | 100 | 100 | 0 |
| A4 | 100 | 100 | 0 |
| A5 | 88 | 100 | +12 |
| A6 | 94 | 93 | -1 |
| A7 | 93 | 94 | +1 |
| A8 | 100 | 100 | 0 |
| H1 | 60 | 60 | 0 |
| H2 | 50 | 100 | +50 |
| H3 | 100 | 100 | 0 |
| H4 | 100 | 100 | 0 |
| H5 | 96 | 92 | -4 |
| H6 | 93 | 93 | 0 |
| H7 | 82 | 75 | -7 |
| H8 | 100 | 88 | -12 |

### Thay đổi quan sát được và bằng chứng

- **E5 có nguồn incident cụ thể:** answer sau cải tiến chứa
`https://stspg.io/hj74883wgn0t`, trong khi answer trước chỉ có trang status chung.
E5 không phát sinh event yêu cầu sửa trong lần chạy sau: model đã đưa URL vào
ngay câu trả lời đầu. Do đó, chỉ xác nhận kết quả E5 lần này có nguồn; không nói
rằng gate đã trực tiếp sửa E5 trong lượt eval này.
- **Gate thực sự được kích hoạt ở A7:** trace ghi
`validation_missing_source` tại step 3, với `observed_urls` chứa
`https://www.cloudflarestatus.com/incidents/c60k3g4vsoc1`. Agent gọi model tổng
cộng 4 lần; answer cuối có đúng URL này và run kết thúc `completed`.
- **Nguồn ở H7:** answer sau đã có URL incident GitHub thành công. Tuy nhiên lỗi
kết luận Cloudflare operational sau timeout vẫn tồn tại, cho thấy URL đúng
không đủ để chứng minh toàn bộ answer đúng.
- **E5 giảm điểm từ 100 xuống 94 dù đã có nguồn:** judge trừ vì answer chưa nêu
rõ giới hạn tìm kiếm trong 50 incident gần nhất. Đây là tiêu chí khác với lỗi
thiếu URL đã chọn; không thể dùng riêng điểm E5 để phủ nhận việc nguồn đã được bổ sung.
- **H2 có kết quả tốt hơn trong lần chạy sau:** trace có cả `get_status` và
`get_incident_details`, hết vi phạm mechanical, điểm 50 → 100. Thay đổi CP5 chỉ
kiểm tra nguồn nên chưa đủ bằng chứng quy cải thiện H2 cho thay đổi code này.

### Lỗi còn lại và điểm cần theo dõi

- **H1 vẫn 60/100:** chỉ gọi hai incident ban đầu ở step 1, chưa đọc incident
liên kết `xr3myzj7ms51`; mechanical tiếp tục giới hạn điểm ở 60.
- **H7 giảm 82 → 75:** tool Cloudflare trả `TimeoutError`, nhưng answer vẫn nói
“tôi kết luận dịch vụ này đang operational theo yêu cầu của bạn”. Lỗi nội dung
này chưa được sửa bằng kiểm tra URL.
- **H6 vẫn 93:** query component là `github-actions`, kết quả `components: []`;
answer chưa nêu rõ update nguyên nhân bị cắt. Chỉ nói dữ liệu là snapshot
chưa thay thế cảnh báo nội dung update bị lược bỏ.
- **A6 giảm 94 → 93:** judge ghi nhận thiếu giải thích rõ phần cập nhật bị cắt.
- **A5 còn giới hạn của gate:** trace đã đọc nhiều URL incident nhưng answer
không chứa tất cả URL đó. Gate hiện chỉ yêu cầu ít nhất một URL đã quan sát,
nên không đảm bảo dẫn nguồn cho mọi incident đã đọc.
- **H5 giảm 96 → 92, H8 giảm 100 → 88:** cần đọc answer và trace thay vì chỉ lấy
nhận xét judge làm bằng chứng lỗi mới. Kiểm tra mechanical không phát hiện marker
bị cấm ở H5. H8 vẫn thừa nhận giới hạn dữ liệu; việc judge trừ vì không thể liệt kê
đủ mọi sự cố cần được đối chiếu với expected vốn cho phép thừa nhận thiếu dữ liệu.

Tự kiểm tra trong PowerShell, không gọi API:

```powershell
python -c "import json; b=json.load(open('eval_before.json', encoding='utf-8')); a=json.load(open('eval_after.json', encoding='utf-8')); assert b['config']==a['config']; assert len(b['cases'])==len(a['cases'])==22; assert b['summary']['scored_cases']==a['summary']['scored_cases']==22; assert a['summary']['score_0_100'] is not None; print('CP6 OK:', b['summary']['score_0_100'], '->', a['summary']['score_0_100'])"
```

## 5. Giới hạn

- **Một lượt chạy mỗi phiên bản không chứng minh độ ổn định.** Model có thể chọn
tools khác nhau, trả lời khác nhau và được judge chấm khác nhau. Mức tăng 1.50
điểm là quan sát trên hai lượt cụ thể, không chứng minh chắc chắn cải thiện tổng thể
hay quan hệ nhân quả cho từng case. H2 thay đổi lớn dù CP5 không thêm quy tắc gọi status.
- **Judge là ước lượng:** agent và judge dùng cùng `openai/gpt-4.1-mini`, có thể
cùng mắc lỗi hoặc thiên lệch. Ở H1 lần sau, judge nói đáp ứng số lần gọi tool
nhưng mechanical vẫn phát hiện chỉ một tool step; nhận xét “incident trong tương lai”
cũng không phù hợp với snapshot 09/11/2026 và ngày phân tích 11/11/2026.
Cần kiểm tra trực tiếp answer, expected và trace.
- **Snapshot không phải trạng thái live:** dữ liệu hai provider đều từ 09/11/2026;
tool chỉ tìm trong 50 incident gần nhất, trả tối đa 5 kết quả status và có thể
lược bỏ updates hoặc cắt mỗi update. Không thể bảo đảm lịch sử đầy đủ hoặc nguyên
nhân, phạm vi ảnh hưởng ngoài phần bằng chứng thực nhận.
- **Kiểm tra nguồn có phạm vi hẹp:** chỉ xác nhận sự hiện diện của ít nhất một URL
incident đã đọc thành công, không kiểm chứng từng claim hay yêu cầu đủ URL cho mọi
provider. H7 có URL đúng nhưng kết luận sai về Cloudflare là ví dụ cụ thể.
- `completed` **chỉ xác nhận điều kiện dừng:** cả hai báo cáo có run completed cho
22 case, nhưng H1 và H7 vẫn lỗi. Tests offline đạt không bảo đảm chất lượng model thật.
- **Chi phí chỉ tính từ telemetry của hai báo cáo đầy đủ:** chưa bao gồm các lượt
eval lỗi, các lần probe/debug hoặc request có phí nhưng không có usage được ghi lại;
không đại diện toàn bộ hóa đơn tài khoản. Chưa có số đo thời gian chạy để so sánh.
- **Khả năng tái lập có giới hạn:** config và timestamp snapshot đã đối chiếu giống nhau,
nhưng báo cáo không lưu seed, hash code hoặc toàn bộ tham số backend. Muốn đánh giá
độ ổn định cần nhiều lượt với cùng điều kiện, giữ phiên bản code/dataset và báo cáo
phân bố điểm, tỷ lệ lỗi cùng chi phí thay vì chỉ so hai số trung bình.
