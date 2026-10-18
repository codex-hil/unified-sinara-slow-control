`timescale 1ns/1ps
// Behavioral model of the ECP5 preset flop used by upstream SPI2WB.
// This isolates logical framing; it does not model pad delays or metastability.
module FD1P3BX(input D, CK, SP, PD, output reg Q = 1);
always @(posedge CK or posedge PD)
    if (PD) Q <= 1; else if (SP) Q <= D;
endmodule

module tb;
reg sys_clk=0, rst=0, sck=0, mosi=0, selected=1;
wire miso,cyc,stb,we;
wire [14:0] adr;
wire [15:0] dat_w;
reg ack=0;
reg [15:0] dat_r=0;
reg [15:0] memory [0:32767];
integer writes=0, reads=0, i;
reg [15:0] got;
bridge d(sys_clk,rst,sck,adr,dat_w,dat_r,cyc,stb,ack,we,mosi,miso,selected);
always #5 sys_clk=~sys_clk;
always @(posedge sys_clk) begin
    ack <= 0;
    if (!rst && cyc && stb && !ack) begin
        ack <= 1;
        if(we) begin memory[adr]<=dat_w; writes<=writes+1; end
        else begin dat_r<=memory[adr]; reads<=reads+1; end
    end
end
task bit_out(input v);
begin mosi=v; #20; sck=1; #20; sck=0; end
endtask
task write_word(input [14:0] a,input [15:0] value);
integer j;
begin
    selected=1;
    bit_out(0);
    for(j=14;j>=0;j=j-1) bit_out(a[j]);
    for(j=15;j>=0;j=j-1) bit_out(value[j]);
    #20; selected=0; #200;
end
endtask
task read_word(input [14:0] a,output [15:0] value);
integer j;
begin
    selected=1;
    bit_out(1);
    for(j=14;j>=0;j=j-1) bit_out(a[j]);
    for(j=0;j<5;j=j+1) bit_out(0);
    for(j=15;j>=0;j=j-1) begin bit_out(0); value[j]=miso; end
    #20; selected=0; #200;
end
endtask
initial begin
    for(i=0;i<32768;i=i+1) memory[i]=0;
    memory[160]=16'haaaa; memory[161]=16'h5555; memory[162]=3;
    #1; rst=1; selected=0;
    #100; rst=0; #200;
    $display("Startup Wishbone writes in behavioral harness: %0d (excluded from transaction checks)",writes);
    writes=0; reads=0; // Startup behavior is not part of the transaction checks.
    read_word(160,got);
    if(got!==16'haaaa) $fatal(1,"ID160 read: %h",got);
    read_word(161,got);
    if(got!==16'h5555) $fatal(1,"ID161 read: %h",got);
    read_word(162,got);
    if(got!==3) $fatal(1,"revision read: %h",got);
    write_word(140,16'habcd);
    if(memory[140]!==16'habcd) $fatal(1,"write 140: %h",memory[140]);
    read_word(140,got);
    if(got!==16'habcd) $fatal(1,"readback 140: %h",got);
    if(writes!==1) $fatal(1,"read caused unwanted writes: %d",writes);
    // Upstream currently produces TWO WB reads per serial read in this model.
    // Record the baseline quirk; do not claim exactly-once semantics.
    if(reads!==8) $fatal(1,"changed baseline read count: %d",reads);
    $display("LIMITATION: %0d Wishbone reads for four serial reads",reads);
    $display("PASS upstream SPI2WB: 25MHz x1, 16-bit header, dummy5, IDs160..162, write/readback140, no read-side writes");
    $finish;
end
initial begin #100000; $fatal(1,"watchdog"); end
endmodule
