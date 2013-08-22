# Run with ./run-tests.sh

start_fake_irnetbox() {
    waitfor() {
        for i in {1..100}; do grep "$1" "$2" && return; sleep 0.1; done;
        return 1
    }

    "$testdir"/fake-irnetbox > fake-irnetbox.log &
    fake_irnetbox=$!
    trap "kill $fake_irnetbox" EXIT
    waitfor "^PORT=" fake-irnetbox.log || fail "fake-irnetbox failed to start"
    irnetbox_port=$(awk -F= '/^PORT=/ { print $2 }' fake-irnetbox.log)
}

test_irnetbox_commands() {
    start_fake_irnetbox

    cat > test.py <<-EOF
	import irnetbox
	rcu = irnetbox.RemoteControlConfig("$testdir/irnetbox.conf")
	with irnetbox.IRNetBox("localhost", $irnetbox_port) as ir:
	    ir.power_on()
	    ir.irsend_raw(port=1, power=100, data=rcu["MENU"])
	    ir.irsend_raw(port=1, power=100, data=rcu["OK"])
	EOF
    python test.py || return
    grep -q "Received message POWER_ON" fake-irnetbox.log ||
        fail "fake-irnetbox didn't receive POWER_ON message"
    [[ "$(grep "Received message OUTPUT_IR_ASYNC" fake-irnetbox.log |
          wc -l)" -eq 2 ]] ||
        fail "fake-irnetbox didn't receive 2 OUTPUT_IR_ASYNC messages"
}

test_stbt_run_irnetbox_control() {
    start_fake_irnetbox

    cat > test.py <<-EOF
	press("MENU")
	press("OK")
	EOF
    stbt-run -v \
        --control irnetbox:localhost:$irnetbox_port:1:"$testdir"/irnetbox.conf \
        test.py || return
    [[ "$(grep "Received message OUTPUT_IR_ASYNC" fake-irnetbox.log |
          wc -l)" -eq 2 ]] ||
        fail "fake-irnetbox didn't receive 2 OUTPUT_IR_ASYNC messages"
}

test_irnetbox_proxy() {
    start_fake_irnetbox
    proxy_port=5887
    "$srcdir"/irnetproxy.py -vv \
        -l localhost -p $proxy_port \
        localhost $irnetbox_port &
    proxy=$!
    trap "kill $fake_irnetbox $proxy" EXIT

    cat > test1.py <<-EOF
	import time
	import irnetbox
	with irnetbox.IRNetBox("localhost", $proxy_port) as ir:
	    for _ in range(10):
	        ir.indicators_on()
	        print "test1.py: Sent CPLD_INSTRUCTION"
	        time.sleep(0.1)
	EOF

    cat > test2.py <<-EOF
	import time
	import irnetbox
	rcu = irnetbox.RemoteControlConfig("$testdir/irnetbox.conf")
	with irnetbox.IRNetBox("localhost", $proxy_port) as ir:
	    for _ in range(10):
	        ir.irsend_raw(port=1, power=100, data=rcu["MENU"])
	        print "test2.py: Sent OUTPUT_IR_ASYNC"
	        time.sleep(0.1)
	EOF

    python test1.py & test1=$!
    python test2.py & test2=$!
    wait $test1 $test2 || return
}
