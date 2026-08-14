CREATE INDEX CONCURRENTLY IF NOT EXISTS fenxiao_customer_health_non_loss_status_idx
ON fenxiao.customer_health_detail (customer_health_status)
WHERE customer_health_status <> '流失';

CREATE INDEX CONCURRENTLY IF NOT EXISTS alibaba_customer_health_non_loss_status_idx
ON alibaba.customer_health_detail (customer_health_status)
WHERE customer_health_status <> '流失';
